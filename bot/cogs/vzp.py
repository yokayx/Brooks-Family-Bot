from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.config import VZP_CHANNEL_ID, VZP_POLL_SECONDS
from bot.roster.manager import is_leader
from bot.vzp.client import VzpClient
from bot.vzp.filter import is_brooks_richman
from bot.vzp.format import build_result_embed
from bot.vzp.store import already_posted, has_any_posted, mark_many_seen, mark_posted

log = logging.getLogger("brooks.vzp")
_NO_MENTIONS = discord.AllowedMentions.none()


class VzpCog(commands.Cog, name="VZP"):
    """Итоги каптов Brooks (Richman) в отдельный канал."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.client = VzpClient()
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
            posted = await self._tick()
            if posted:
                log.info("posted %s vzp results", posted)
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
            posted = await self._tick()
        except Exception as exc:
            log.exception("manual vzp poll")
            await interaction.followup.send(f"Ошибка: `{exc}`", ephemeral=True)
            return
        await interaction.followup.send(f"Новых итогов: {posted}.", ephemeral=True)

    async def _tick(self) -> int:
        async with self._lock:
            wars = await self.client.recent_wars()
            ours = [war for war in wars if is_brooks_richman(war) and war.get("id")]
            finished = [war for war in ours if str(war.get("status") or "") == "finished"]

            if not await has_any_posted():
                seen = [str(war["id"]) for war in finished]
                seen.append("__vzp_bootstrapped__")
                await mark_many_seen(seen)
                log.info("vzp bootstrap: marked %s finished wars as seen", len(finished))
                return 0

            channel = await self._channel()
            if channel is None:
                return 0

            posted = 0
            for war in reversed(finished):
                war_id = str(war["id"])
                if await already_posted(war_id):
                    continue
                detail = await self.client.war_detail(war_id)
                embed = build_result_embed(detail)
                message = await channel.send(embed=embed, allowed_mentions=_NO_MENTIONS)
                await mark_posted(war_id, message.id)
                posted += 1
                await asyncio.sleep(0.4)
            return posted

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
