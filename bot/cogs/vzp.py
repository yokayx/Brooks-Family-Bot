from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.config import VZP_CHANNEL_ID, VZP_POLL_SECONDS
from bot.roster.manager import is_leader
from bot.vzp.client import VzpClient
from bot.vzp.filter import is_brooks_richman, is_finished
from bot.vzp.format import build_result_embed
from bot.vzp.store import already_posted, has_any_posted, mark_posted

log = logging.getLogger("brooks.vzp")
_NO_MENTIONS = discord.AllowedMentions.none()
_BOOTSTRAP_SENTINEL = "__vzp_bootstrapped__"


@dataclass
class VzpReport:
    """Что дал один проход опроса — для логов и `/vzp`."""

    scanned: int = 0
    candidates: int = 0
    posted: int = 0
    pending: int = 0
    skipped: int = 0
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        parts = [
            f"просмотрено войн: {self.scanned}",
            f"нашло Brooks/Richman: {self.candidates}",
            f"отправлено: {self.posted}",
        ]
        if self.pending:
            parts.append(f"ещё идёт: {self.pending}")
        if self.skipped:
            parts.append(f"отмечено без отправки: {self.skipped}")
        if self.error:
            parts.append(f"ошибка: {self.error}")
        return "\n".join(parts)


class VzpCog(commands.Cog, name="VZP"):
    """Итоги каптов Brooks (Richman) в отдельный канал."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.client = VzpClient()
        self.last_report: VzpReport | None = None
        self._lock = asyncio.Lock()

    async def cog_load(self) -> None:
        await self.client.start()
        if not self.poll_results.is_running():
            self.poll_results.start()

    async def cog_unload(self) -> None:
        self.poll_results.cancel()
        await self.client.close()

    @tasks.loop(seconds=VZP_POLL_SECONDS)
    async def poll_results(self) -> None:
        try:
            report = await self._tick()
            self.last_report = report
            if report.posted:
                log.info("vzp: отправлено итогов: %s", report.posted)
            elif report.error:
                log.warning("vzp: %s", report.as_text().replace("\n", "; "))
        except Exception:
            log.exception("vzp poll failed")

    @poll_results.before_loop
    async def before_poll(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="vzp", description="Проверить новые итоги ВЗП (руководство)")
    async def vzp_now(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not is_leader(member):
            await interaction.response.send_message("Нет прав.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            report = await self._tick()
        except Exception as exc:
            log.exception("manual vzp poll")
            await interaction.followup.send(f"Ошибка: `{exc}`", ephemeral=True)
            return
        self.last_report = report
        text = report.as_text()
        if self.client.last_error:
            text += f"\nпоследняя ошибка запроса: `{self.client.last_error}`"
        await interaction.followup.send(text, ephemeral=True)

    async def _tick(self) -> VzpReport:
        async with self._lock:
            wars = await self.client.recent_wars()
            candidates = [war for war in wars if is_brooks_richman(war) and war.get("id")]
            report = VzpReport(scanned=len(wars), candidates=len(candidates))
            if not candidates:
                return report

            # Первый запуск: историю не спамим, только помечаем доигранное.
            bootstrapping = not await has_any_posted()
            channel = None if bootstrapping else await self._channel()
            if not bootstrapping and channel is None:
                report.error = f"канал ВЗП {VZP_CHANNEL_ID} недоступен"
                return report

            for war in reversed(candidates):  # старые вперёд
                war_id = str(war["id"])
                if await already_posted(war_id):
                    continue
                try:
                    detail = await self.client.war_detail(war_id)
                except Exception as exc:
                    log.warning("vzp detail %s failed", war_id, exc_info=True)
                    report.error = f"детали войны {war_id}: {exc}"
                    continue
                if not is_brooks_richman(detail):
                    continue
                if not is_finished(detail):
                    report.pending += 1  # бой ещё идёт — возьмём следующим проходом
                    continue
                if bootstrapping:
                    await mark_posted(war_id, None)
                    report.skipped += 1
                    continue
                assert channel is not None
                embed = build_result_embed(detail)
                message = await channel.send(embed=embed, allowed_mentions=_NO_MENTIONS)
                await mark_posted(war_id, message.id)
                report.posted += 1
                await asyncio.sleep(0.4)

            if bootstrapping:
                await mark_posted(_BOOTSTRAP_SENTINEL, None)
                report.notes.append("первый запуск: история не отправлялась")
            return report

    async def _channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(VZP_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(VZP_CHANNEL_ID)
            except discord.HTTPException:
                log.exception("vzp channel not found")
                return None
        if not isinstance(channel, discord.TextChannel):
            log.error("vzp channel is not text")
            return None
        return channel


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VzpCog(bot))
