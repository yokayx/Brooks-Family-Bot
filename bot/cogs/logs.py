"""Ког логирования: категории логов, инвайт-трекер, live-терминал.

Порт кога из KillaBot на структуру Brooks: каналы — константы ``bot/config.py``
(вместо строк Dashboard), БД — ``bot/db.session_scope``, медиа храним в
``data/log_attachments``. Логи уходят эмбедами.
"""

from __future__ import annotations

import asyncio
import difflib
import glob
import io
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

import aiohttp
import discord
from discord.ext import commands, tasks
from sqlalchemy import select

from bot.config import (
    LOG_AUDIT_CHANNEL_ID,
    LOG_BOT_LIVE_CHANNEL_ID,
    LOG_INVITE_CHANNEL_ID,
    LOG_MEMBER_CHANNEL_ID,
    LOG_MODERATION_CHANNEL_ID,
    LOG_SERVER_CHANNEL_ID,
    LOG_TEXT_CHANNEL_ID,
    LOG_VOICE_CHANNEL_ID,
    ROSTER_CHANNEL_ID,
)
from bot.db import session_scope
from bot.models import MemberStat

if TYPE_CHECKING:
    from bot.main import BrooksBot

try:  # сжатие картинок для «удалённого сообщения» — необязательно
    from PIL import Image
except ImportError:  # Pillow не установлен — сохраняем вложения как есть
    Image = None

log = logging.getLogger("brooks.logs")

ATTACHMENTS_DIR = "data/log_attachments"
# Сколько живут скачанные вложения (секунды)
ATTACHMENT_TTL_SECONDS = 24 * 3600
# Больше 25 МБ в лог всё равно не прикрепить (лимит Discord)
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def utc_now() -> datetime:
    return datetime.now(UTC)


def truncate(text: str | None, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)] + "..."


def truncate_codeblock(text: str, limit: int, *, lang: str = "") -> str:
    body = truncate(text, max(limit - len(lang) - 8, 10))
    return f"```{lang}\n{body}\n```"


def humanize_age(created_at: datetime | None) -> str:
    """`5 д.`, `2 мес.`, `1 г.` — возраст аккаунта."""
    if created_at is None:
        return "неизвестно"
    delta = utc_now() - created_at
    if delta < timedelta(0):
        return "только что"
    years, rest = divmod(delta.days, 365)
    months = rest // 30
    if years:
        return f"{years} г."
    if months:
        return f"{months} мес."
    return f"{delta.days} д."


async def _bump_joins(user_id: int) -> tuple[int, int]:
    async with session_scope() as session:
        result = await session.execute(select(MemberStat).where(MemberStat.user_id == user_id))
        stat = result.scalar_one_or_none()
        if stat is None:
            stat = MemberStat(user_id=user_id, joins_count=1, leaves_count=0)
            session.add(stat)
        else:
            stat.joins_count = (stat.joins_count or 0) + 1
        await session.flush()
        return stat.joins_count or 0, stat.leaves_count or 0


async def _bump_leaves(user_id: int) -> tuple[int, int]:
    async with session_scope() as session:
        result = await session.execute(select(MemberStat).where(MemberStat.user_id == user_id))
        stat = result.scalar_one_or_none()
        if stat is None:
            stat = MemberStat(user_id=user_id, joins_count=0, leaves_count=1)
            session.add(stat)
        else:
            stat.leaves_count = (stat.leaves_count or 0) + 1
        await session.flush()
        return stat.joins_count or 0, stat.leaves_count or 0


class DiscordLoggingHandler(logging.Handler):
    """Трансляция журнала Python в канал ``bot-live`` (живая консоль).

    Очередь ограничена: при флуде лишнее отбрасывается oldest-first, а не
    растёт в памяти. Отправка пачками, текст подрезан под лимит Discord.
    """

    MAX_QUEUE = 500
    BATCH_LIMIT = 8
    MAX_PAYLOAD = 1900

    def __init__(self, bot: BrooksBot) -> None:
        super().__init__()
        self.bot = bot
        self.queue: list[str] = []
        self.dropped = 0
        self._task = self.bot.loop.create_task(self.flush_logs_loop())

    def emit(self, record: logging.LogRecord) -> None:
        name = record.name or ""
        # Свои логи и логи библиотек в Discord не транслируем — иначе рекурсия.
        if name.startswith(("discord", "asyncio", "websockets")) or name in {
            "brooks.logs",
            "brooks.live",
        }:
            return
        try:
            entry = self.format(record)
        except Exception:  # noqa: BLE001
            return

        if len(self.queue) >= self.MAX_QUEUE:
            try:
                self.queue.pop(0)
            except IndexError:
                return
            self.dropped += 1
            return
        self.queue.append(entry)

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def flush_logs_loop(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            if not self.queue:
                await asyncio.sleep(2.0)
                continue

            batch = self.queue[: self.BATCH_LIMIT]
            del self.queue[: len(batch)]

            text = "\n".join(batch)
            if self.dropped:
                text += f"\n... [пропущено записей: {self.dropped}]"
                self.dropped = 0

            logs_cog = self.bot.get_cog("Logs")
            channel = None
            if logs_cog is not None:
                channel = await logs_cog.get_log_channel("bot-live")
            if channel is not None:
                try:
                    await channel.send(truncate_codeblock(text, 1990, lang="text"))
                except discord.DiscordException as exc:
                    log.debug("live-console: не отправили пакет логов: %s", exc)
            await asyncio.sleep(2.0)


class LogsCog(commands.Cog, name="Logs"):
    """Автоматическое логирование действий пользователей по категориям."""

    # Категория -> константа канала в bot/config.py
    CATEGORY_CHANNELS: ClassVar[dict[str, int]] = {
        "moderation": LOG_MODERATION_CHANNEL_ID,
        "voice": LOG_VOICE_CHANNEL_ID,
        "text": LOG_TEXT_CHANNEL_ID,
        "member": LOG_MEMBER_CHANNEL_ID,
        "invite": LOG_INVITE_CHANNEL_ID,
        "server": LOG_SERVER_CHANNEL_ID,
        "audit": LOG_AUDIT_CHANNEL_ID,
        "bot-live": LOG_BOT_LIVE_CHANNEL_ID,
    }

    def __init__(self, bot: BrooksBot) -> None:
        self.bot = bot
        # Кэш инвайтов: {guild_id: list[Invite]}
        self.invite_cache: dict[int, list[discord.Invite]] = {}
        # Кэш использований Vanity URL: {guild_id: uses}
        self.vanity_cache: dict[int, int] = {}
        self._dl_session: aiohttp.ClientSession | None = None
        self._dl_sem = asyncio.Semaphore(4)
        self._live_handler: DiscordLoggingHandler | None = None
        self.prune_attachments.start()

    def cog_unload(self) -> None:
        self.prune_attachments.cancel()
        if self._dl_session is not None and not self._dl_session.closed:
            self.bot.loop.create_task(self._dl_session.close())
            self._dl_session = None
        handler, self._live_handler = self._live_handler, None
        if handler is not None:
            try:
                logging.getLogger().removeHandler(handler)
            except Exception:  # noqa: BLE001
                pass
            try:
                handler.cancel()
            except Exception:  # noqa: BLE001
                pass

    # ---------- каналы и отправка ----------

    async def get_log_channel(self, category: str) -> discord.TextChannel | None:
        """Канал категории. id = 0 в конфиге — значит категория не настроена."""
        channel_id = self.CATEGORY_CHANNELS.get(category)
        if not channel_id:
            log.debug("логи: категория %r не настроена (id=0)", category)
            return None

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                log.exception("логи: канал %s недоступен", channel_id)
                return None
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            log.warning(
                "логи: канал %s для категории %r не текстовый (%s)",
                channel_id,
                category,
                type(channel).__name__,
            )
            return None
        return channel

    @staticmethod
    def _snapshot_files(files: list[discord.File] | None) -> list[tuple[bytes, str]]:
        """Байты вложений снимаем ДО отправки: discord.py закроет файлы после send."""
        if not files:
            return []
        snapshots: list[tuple[bytes, str]] = []
        for file in files:
            fp = getattr(file, "fp", None)
            name = getattr(file, "filename", None) or "file"
            if fp is None or not hasattr(fp, "read"):
                continue
            try:
                position = fp.tell() if hasattr(fp, "tell") else 0
                if hasattr(fp, "seek"):
                    fp.seek(0)
                data = fp.read()
                if hasattr(fp, "seek"):
                    fp.seek(position)
                if data:
                    snapshots.append((bytes(data), name))
            except Exception:  # noqa: BLE001
                log.debug("логи: не сняли байты файла %s", name)
        return snapshots

    @staticmethod
    def _build_files(snapshots: list[tuple[bytes, str]]) -> list[discord.File] | None:
        if not snapshots:
            return None
        built: list[discord.File] = []
        for data, name in snapshots:
            try:
                built.append(discord.File(io.BytesIO(data), filename=name))
            except Exception:  # noqa: BLE001
                log.debug("логи: не собрали файл %s", name)
        return built or None

    async def safe_send_log(
        self,
        category: str,
        embed: discord.Embed,
        files: list[discord.File] | None = None,
    ) -> None:
        """Лог в канал категории + дубль в audit (кроме самой категории audit)."""
        snapshots = self._snapshot_files(files)

        channel = await self.get_log_channel(category)
        if channel is not None:
            try:
                await channel.send(embed=embed, files=self._build_files(snapshots))
            except discord.Forbidden:
                log.warning("нет прав на отправку логов в %s (%s)", channel.id, category)
            except discord.HTTPException:
                log.exception("не отправили лог в %s", channel.id)

        if category == "audit":
            return

        audit_channel = await self.get_log_channel("audit")
        if audit_channel is None or audit_channel == channel:
            return
        try:
            await audit_channel.send(embed=embed, files=self._build_files(snapshots))
        except discord.DiscordException:
            log.warning("логи: не продублировали %s в audit", category)

    async def get_audit_executor(
        self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int
    ) -> discord.abc.User | None:
        try:
            async for entry in guild.audit_logs(limit=3, action=action):
                if entry.target is not None and entry.target.id == target_id:
                    return entry.user
        except discord.HTTPException:
            log.debug("логи: нет доступа к аудит-логу (%s)", action)
        return None

    def _is_our_guild(self, guild: discord.Guild | None) -> bool:
        if guild is None:
            return False
        channel = self.bot.get_channel(ROSTER_CHANNEL_ID)
        if isinstance(channel, discord.abc.GuildChannel):
            return channel.guild.id == guild.id
        return True

    # ---------- вложения ----------

    async def _attachment_session(self) -> aiohttp.ClientSession:
        if self._dl_session is None or self._dl_session.closed:
            self._dl_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self._dl_session

    async def download_attachment(self, attachment: discord.Attachment, message_id: int) -> None:
        """Скачиваем вложение заранее — к моменту удаления ссылка уже мертва."""
        if (attachment.size or 0) > MAX_ATTACHMENT_BYTES:
            return
        try:
            session = await self._attachment_session()
            async with self._dl_sem, session.get(attachment.url) as response:
                if response.status != 200:
                    return
                data = await response.read()
        except Exception:  # noqa: BLE001
            log.debug("логи: не скачали вложение %s", attachment.filename)
            return

        try:
            os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
            path = os.path.join(ATTACHMENTS_DIR, f"{message_id}_{attachment.filename}")
            is_image = attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            if not is_image:
                if (attachment.size or 0) >= 8 * 1024 * 1024:
                    return
                with open(path, "wb") as handle:
                    handle.write(data)
                return

            if Image is None:
                with open(path, "wb") as handle:
                    handle.write(data)
                return

            def compress() -> None:
                image = Image.open(io.BytesIO(data))
                if image.mode in ("RGBA", "P"):
                    image = image.convert("RGB")
                image.save(path, "JPEG", quality=40, optimize=True)

            try:
                await asyncio.get_running_loop().run_in_executor(None, compress)
            except Exception:  # noqa: BLE001
                with open(path, "wb") as handle:
                    handle.write(data)
        except Exception:  # noqa: BLE001
            log.debug("логи: не сохранили вложение %s", attachment.filename)

    @tasks.loop(hours=2)
    async def prune_attachments(self) -> None:
        if not os.path.exists(ATTACHMENTS_DIR):
            return
        now = time.time()
        for filename in os.listdir(ATTACHMENTS_DIR):
            path = os.path.join(ATTACHMENTS_DIR, filename)
            if not os.path.isfile(path):
                continue
            if now - os.path.getmtime(path) > ATTACHMENT_TTL_SECONDS:
                try:
                    os.remove(path)
                except OSError:
                    log.debug("логи: не удалили %s", path)

    # ---------- старт ----------

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await asyncio.sleep(1)
        for guild in self.bot.guilds:
            try:
                self.invite_cache[guild.id] = await guild.invites()
                log.info(
                    "логи: кэш инвайтов %s — %s шт.", guild.name, len(self.invite_cache[guild.id])
                )
            except discord.Forbidden:
                log.warning("логи: нет прав на инвайты сервера %s", guild.name)
            except discord.HTTPException:
                log.exception("логи: не прочитали инвайты %s", guild.name)

            if "VANITY_URL" in guild.features:
                try:
                    vanity = await guild.vanity_invite()
                    self.vanity_cache[guild.id] = vanity.uses
                except discord.DiscordException:
                    log.debug("логи: нет Vanity URL у %s", guild.name)

        # on_ready бывает несколько раз (переподключения) — хендлер подключаем один.
        root = logging.getLogger()
        if self._live_handler is None and not any(
            isinstance(existing, DiscordLoggingHandler) for existing in root.handlers
        ):
            handler = DiscordLoggingHandler(self.bot)
            handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
            )
            root.addHandler(handler)
            self._live_handler = handler

    # ---------- инвайты ----------

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        guild = invite.guild
        if guild is None:
            return
        cached = self.invite_cache.setdefault(guild.id, [])
        self.invite_cache[guild.id] = [inv for inv in cached if inv.code != invite.code] + [invite]

        embed = discord.Embed(
            title="🔗 Создано приглашение",
            color=discord.Color.green(),
            timestamp=utc_now(),
        )
        inviter = invite.inviter
        embed.description = (
            f"Код: `{invite.code}`\n"
            f"Пригласил: {inviter.mention if inviter else '—'}"
            f" (`{inviter.id if inviter else '—'}`)\n"
            f"Канал: {invite.channel.mention if invite.channel else '—'}\n"
            f"Максимум использований: {invite.max_uses or 'без ограничения'}\n"
            f"Срок жизни: {f'{invite.max_age // 3600} ч.' if invite.max_age else 'бессрочное'}"
        )
        await self.safe_send_log("invite", embed)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        guild = invite.guild
        if guild is None:
            return
        if guild.id in self.invite_cache:
            self.invite_cache[guild.id] = [
                inv for inv in self.invite_cache[guild.id] if inv.code != invite.code
            ]
        embed = discord.Embed(
            title="✂️ Приглашение удалено",
            description=f"Код `{invite.code}` больше не действует.",
            color=discord.Color.red(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("invite", embed)

    # ---------- сообщения ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        for attachment in message.attachments:
            self.bot.loop.create_task(self.download_attachment(attachment, message.id))

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return

        executor = await self.get_audit_executor(
            message.guild, discord.AuditLogAction.message_delete, message.author.id
        )
        who_deleted = (
            f"❌ Модератор {executor.mention}"
            if executor
            else f"👤 Автор сообщения {message.author.mention} самостоятельно"
        )

        embed = discord.Embed(
            title="🗑️ Сообщение было удалено",
            color=discord.Color.red(),
            timestamp=utc_now(),
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="💬 Канал", value=message.channel.mention, inline=True)
        embed.add_field(name="🗑️ Кто удалил", value=who_deleted, inline=True)
        embed.add_field(
            name="📄 Текст сообщения",
            value=truncate(message.content, 1024) or "*[Вложение или пустое сообщение]*",
            inline=False,
        )

        files: list[discord.File] = []
        cached = glob.glob(os.path.join(ATTACHMENTS_DIR, f"{message.id}_*"))
        for path in cached:
            if os.path.exists(path):
                filename = os.path.basename(path)
                clean = filename.split("_", 1)[-1] if "_" in filename else filename
                files.append(discord.File(path, filename=clean))

        await self.safe_send_log("text", embed, files=files)

        for path in cached:
            try:
                os.remove(path)
            except OSError:
                log.debug("логи: не удалили %s", path)

    def generate_text_diff(self, before_text: str, after_text: str) -> str:
        diff = difflib.ndiff(before_text.split(), after_text.split())
        result = []
        for item in diff:
            if item.startswith("- "):
                result.append(f"~~{item[2:]}~~")
            elif item.startswith("+ "):
                result.append(f"**{item[2:]}**")
            elif item.startswith("  "):
                result.append(item[2:])
        return truncate(" ".join(result), 1000)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or before.guild is None or before.content == after.content:
            return
        embed = discord.Embed(
            title="📝 Сообщение было отредактировано",
            color=discord.Color.orange(),
            timestamp=utc_now(),
        )
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.add_field(name="💬 Канал", value=before.channel.mention, inline=True)
        embed.add_field(
            name="📊 Изменения",
            value=self.generate_text_diff(before.content, after.content)
            or "*[Изменения отсутствуют]*",
            inline=False,
        )
        await self.safe_send_log("text", embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages:
            return
        guild = messages[0].guild
        channel = messages[0].channel
        executor = await self.get_audit_executor(
            guild, discord.AuditLogAction.message_bulk_delete, channel.id
        )
        embed = discord.Embed(
            title="🗑️ Сообщения были очищены",
            description=(
                f"В канале {channel.mention} очищено **{len(messages)}** сообщений.\n"
                f"🛡️ **Инициатор очистки:** {executor.mention if executor else 'Система / Бот'}"
            ),
            color=discord.Color.red(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("server", embed)

    # ---------- войс и трибуны ----------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if not self._is_our_guild(member.guild):
            return
        embed = discord.Embed(timestamp=utc_now(), color=discord.Color.blue())
        embed.set_author(name=f"{member} ({member.id})", icon_url=member.display_avatar.url)

        if before.channel is None and after.channel is not None:
            if after.channel.type == discord.ChannelType.stage_voice:
                embed.title = "🎭 Участник зашёл на трибуну"
                embed.description = f"{member.mention} зашёл на трибуну {after.channel.mention}"
            else:
                embed.title = "🔊 Участник зашёл в войс"
                embed.description = f"{member.mention} зашёл в войс {after.channel.mention}"
        elif before.channel is not None and after.channel is None:
            if before.channel.type == discord.ChannelType.stage_voice:
                embed.title = "🎭 Участник вышел с трибуны"
                embed.description = f"{member.mention} вышел с трибуны {before.channel.mention}"
            else:
                embed.title = "🔇 Участник покинул голосовой канал"
                embed.description = f"{member.mention} вышел из войса {before.channel.mention}"
        elif (
            before.channel is not None
            and after.channel is not None
            and before.channel != after.channel
        ):
            embed.title = "🔄 Переход из канала в канал"
            embed.description = (
                f"{member.mention} перешёл из {before.channel.mention} в {after.channel.mention}"
            )
        else:
            return

        await self.safe_send_log("voice", embed)

    @commands.Cog.listener()
    async def on_stage_instance_create(self, stage: discord.StageInstance) -> None:
        embed = discord.Embed(
            title="🎭 Трибуна открыта",
            description=(
                f"Мероприятие на трибуне {stage.channel.mention}!\n**Тема:** `{stage.topic}`"
            ),
            color=discord.Color.green(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("voice", embed)

    @commands.Cog.listener()
    async def on_stage_instance_delete(self, stage: discord.StageInstance) -> None:
        embed = discord.Embed(
            title="🎭 Трибуна закрыта",
            description=f"Мероприятие на трибуне `#{stage.channel.name}` завершено.",
            color=discord.Color.red(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("voice", embed)

    @commands.Cog.listener()
    async def on_stage_instance_update(
        self, before: discord.StageInstance, after: discord.StageInstance
    ) -> None:
        embed = discord.Embed(
            title="🎭 Трибуна обновлена",
            description=(
                f"Тема трибуны {after.channel.mention} изменена.\n"
                f"❌ **Было:** `{before.topic}`\n"
                f"✅ **Стало:** `{after.topic}`"
            ),
            color=discord.Color.orange(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("voice", embed)

    # ---------- участники ----------

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if not self._is_our_guild(after.guild):
            return

        if before.display_name != after.display_name:
            embed = discord.Embed(
                title="👤 Никнейм участника был изменён",
                description=f"Никнейм {after.mention} был изменён.",
                color=discord.Color.blue(),
                timestamp=utc_now(),
            )
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            embed.add_field(name="❌ Было", value=truncate(before.display_name, 1024), inline=True)
            embed.add_field(name="✅ Стало", value=truncate(after.display_name, 1024), inline=True)
            await self.safe_send_log("member", embed)
            return

        if before.roles != after.roles:
            added = [role.mention for role in after.roles if role not in before.roles]
            removed = [role.mention for role in before.roles if role not in after.roles]
            if not (added or removed):
                return
            executor = await self.get_role_update_executor(after)
            embed = discord.Embed(
                title="🎖️ Обновлены роли участника",
                description=(
                    f"Обновлены роли {after.mention}.\n"
                    f"🛡️ **Кем изменено:** {executor.mention if executor else 'Бот / Система'}"
                ),
                color=discord.Color.purple(),
                timestamp=utc_now(),
            )
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            if added:
                embed.add_field(
                    name="🟢 Выданы роли", value=truncate(", ".join(added), 1024), inline=False
                )
            if removed:
                embed.add_field(
                    name="🔴 Сняты роли", value=truncate(", ".join(removed), 1024), inline=False
                )
            await self.safe_send_log("member", embed)

    async def get_role_update_executor(self, member: discord.Member) -> discord.abc.User | None:
        try:
            async for entry in member.guild.audit_logs(
                limit=3, action=discord.AuditLogAction.member_role_update
            ):
                if entry.target is None or entry.target.id != member.id:
                    continue
                if (utc_now() - entry.created_at).total_seconds() < 5:
                    return entry.user
        except discord.HTTPException:
            log.debug("логи: нет доступа к аудит-логу ролей")
        return None

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        if before.avatar == after.avatar:
            return
        guild = None
        for candidate in self.bot.guilds:
            if candidate.get_member(after.id) is not None:
                guild = candidate
                break
        if guild is None or not self._is_our_guild(guild):
            return
        member = guild.get_member(after.id)
        if member is None:
            return

        embed = discord.Embed(
            title="🖼️ Аватарка участника была изменена",
            description=f"{member.mention} обновил изображение профиля.",
            color=discord.Color.blue(),
            timestamp=utc_now(),
        )
        embed.set_author(name=f"{member} ({member.id})", icon_url=after.display_avatar.url)
        if before.avatar:
            embed.add_field(
                name="❌ Было",
                value=f"[Ссылка на аватар]({before.display_avatar.url})",
                inline=True,
            )
        embed.add_field(
            name="✅ Стало", value=f"[Ссылка на аватар]({after.display_avatar.url})", inline=True
        )
        embed.set_thumbnail(url=after.display_avatar.url)
        await self.safe_send_log("member", embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        guild = member.guild
        if not self._is_our_guild(guild):
            return

        try:
            joins, leaves = await _bump_joins(member.id)
        except Exception:  # noqa: BLE001
            log.exception("логи: не учли заход %s", member.id)
            joins, leaves = 1, 0

        invite_used: discord.Invite | None = None
        total_inviter_uses = 0
        is_vanity = False

        try:
            current = await guild.invites()
            old = self.invite_cache.get(guild.id, [])
            old_by_code = {invite.code: invite for invite in old}

            for invite in current:
                previous = old_by_code.get(invite.code)
                if previous is not None and invite.uses > previous.uses:
                    invite_used = invite
                    break
            if invite_used is None:
                for invite in current:
                    if invite.code not in old_by_code and invite.uses > 0:
                        invite_used = invite
                        break

            self.invite_cache[guild.id] = current

            if invite_used is not None and invite_used.inviter is not None:
                total_inviter_uses = sum(
                    invite.uses
                    for invite in current
                    if invite.inviter is not None and invite.inviter.id == invite_used.inviter.id  # type: ignore[union-attr]
                )

            if invite_used is None and "VANITY_URL" in guild.features:
                try:
                    vanity = await guild.vanity_invite()
                    if vanity.uses > self.vanity_cache.get(guild.id, 0):
                        is_vanity = True
                        self.vanity_cache[guild.id] = vanity.uses
                except discord.DiscordException:
                    log.debug("логи: не прочитали Vanity URL")
        except discord.Forbidden:
            log.warning("логи: нет прав на инвайты сервера %s", guild.name)
        except discord.HTTPException:
            log.exception("логи: не определили инвайт")

        if invite_used is not None and invite_used.inviter is not None:
            inviter_info = (
                f"Участника пригласил **{invite_used.inviter.name}** "
                f"(ID: **{invite_used.inviter.id}**) по ссылке **{invite_used.code}**. "
                f"Инвайт использован **{invite_used.uses}** раз. "
                f"Всего приглашений у него — **{total_inviter_uses}**."
            )
        elif is_vanity:
            inviter_info = "Участник зашёл по персональной ссылке сервера (Vanity URL)."
        else:
            inviter_info = (
                "Пригласителя определить не удалось "
                "(системный код, интеграция или зашёл по приглашению бота)."
            )

        created_at = member.created_at.strftime("%d.%m.%Y, %H:%M:%S")
        description = (
            f"**@{member.name}** ({member.mention}) зашёл на сервер. ID: **{member.id}**.\n"
            f"Аккаунт создан **{created_at}** ({humanize_age(member.created_at)}).\n"
            f"Участник был на сервере **{joins}** раз, выходил **{leaves}** раз.\n"
            f"{inviter_info}"
        )
        embed = discord.Embed(
            title="📥 Присоединился новый участник",
            description=truncate(description, 4096),
            color=discord.Color.green(),
            timestamp=utc_now(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.safe_send_log("invite", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        guild = member.guild
        if not self._is_our_guild(guild):
            return

        try:
            joins, leaves = await _bump_leaves(member.id)
        except Exception:  # noqa: BLE001
            log.exception("логи: не учли выход %s", member.id)
            joins, leaves = 1, 1

        executor, action = await self._detect_removal(guild, member.id)

        if action == "kick":
            embed = discord.Embed(
                title="👢 Участник был кикнут",
                description=(
                    f"{member.mention} кикнут модератором "
                    f"{executor.mention if executor else 'Система'}."
                ),
                color=discord.Color.red(),
                timestamp=utc_now(),
            )
        elif action == "ban":
            embed = discord.Embed(
                title="🔨 Участник был забанен",
                description=(
                    f"{member.mention} забанен модератором "
                    f"{executor.mention if executor else 'Система'}."
                ),
                color=discord.Color.dark_red(),
                timestamp=utc_now(),
            )
        else:
            embed = discord.Embed(
                title="📤 Участник покинул сервер",
                description=(
                    f"**@{member.name}** ({member.mention}) покинул сервер.\n"
                    f"Был на сервере: {joins} раз. Выходил: {leaves} раз."
                ),
                color=discord.Color.red(),
                timestamp=utc_now(),
            )
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.safe_send_log("moderation" if action else "invite", embed)

    async def _detect_removal(
        self, guild: discord.Guild, member_id: int
    ) -> tuple[discord.abc.User | None, str | None]:
        """Кик и бан видны как «выход» — отличаем по аудит-логу за последние 5 сек."""
        for action, name in (
            (discord.AuditLogAction.kick, "kick"),
            (discord.AuditLogAction.ban, "ban"),
        ):
            try:
                async for entry in guild.audit_logs(limit=3, action=action):
                    if entry.target is None or entry.target.id != member_id:
                        continue
                    if (utc_now() - entry.created_at).total_seconds() < 5:
                        return entry.user, name
            except discord.HTTPException:
                log.debug("логи: нет доступа к аудит-логу (%s)", action)
        return None, None

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        embed = discord.Embed(
            title="🟢 Бот был добавлен на сервер",
            description=f"Бот присоединился к серверу **{guild.name}**!",
            color=discord.Color.green(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("server", embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log.info("бот покинул сервер %s", guild.name)

    # ---------- свои события модерации (если их кто-то диспатчит) ----------

    @commands.Cog.listener()
    async def on_member_warn_custom(
        self, member: discord.Member, moderator: discord.Member, case_no: int, reason: str
    ) -> None:
        embed = discord.Embed(
            title="⚠️ Участник получил предупреждение",
            description=(
                f"**Участник:** {member.mention} (`{member.id}`)\n"
                f"🛡️ **Модератор:** {moderator.mention}\n"
                f"📝 **Инцидент:** `Случай №{case_no}`\n"
                f"💬 **Причина:** *{truncate(reason, 1000)}*"
            ),
            color=discord.Color.orange(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("moderation", embed)

    @commands.Cog.listener()
    async def on_member_unwarn_custom(
        self, member: discord.Member | int, moderator: discord.Member, case_id: int
    ) -> None:
        mention = member.mention if isinstance(member, discord.Member) else f"ID: {member}"
        embed = discord.Embed(
            title="🔄 Предупреждение было снято",
            description=(
                f"С {mention} снято предупреждение **Случай №{case_id}**.\n"
                f"🛡️ **Снял:** {moderator.mention}"
            ),
            color=discord.Color.green(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("moderation", embed)

    @commands.Cog.listener()
    async def on_member_mute_custom(
        self, member: discord.Member, moderator: discord.Member, duration: str, reason: str
    ) -> None:
        embed = discord.Embed(
            title="🔇 Участник был замьючен",
            description=(
                f"**Участник:** {member.mention}\n"
                f"🛡️ **Модератор:** {moderator.mention}\n"
                f"🕒 **Срок:** `{duration}`\n"
                f"💬 **Причина:** *{truncate(reason, 1000)}*"
            ),
            color=discord.Color.red(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("moderation", embed)

    @commands.Cog.listener()
    async def on_member_unmute_custom(
        self, member: discord.Member, moderator: discord.Member
    ) -> None:
        embed = discord.Embed(
            title="🔊 Участник был размьючен",
            description=(f"**Участник:** {member.mention}\n🛡️ **Модератор:** {moderator.mention}"),
            color=discord.Color.green(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("moderation", embed)

    @commands.Cog.listener()
    async def on_member_kick_custom(
        self, member: discord.Member, moderator: discord.Member, reason: str
    ) -> None:
        embed = discord.Embed(
            title="👢 Участник был кикнут",
            description=(
                f"**Участник:** {member.mention}\n"
                f"🛡️ **Модератор:** {moderator.mention}\n"
                f"💬 **Причина:** *{truncate(reason, 1000)}*"
            ),
            color=discord.Color.red(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("moderation", embed)

    @commands.Cog.listener()
    async def on_member_ban_custom(
        self, member: discord.Member, moderator: discord.Member, reason: str
    ) -> None:
        embed = discord.Embed(
            title="🔨 Участник был забанен",
            description=(
                f"**Участник:** {member.mention}\n"
                f"🛡️ **Модератор:** {moderator.mention}\n"
                f"💬 **Причина:** *{truncate(reason, 1000)}*"
            ),
            color=discord.Color.red(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("moderation", embed)

    @commands.Cog.listener()
    async def on_member_unban_custom(
        self, user: discord.User | int, moderator: discord.Member
    ) -> None:
        mention = user.mention if isinstance(user, discord.User) else f"ID: {user}"
        embed = discord.Embed(
            title="🔓 Участник был разбанен",
            description=f"**Участник:** {mention}\n🛡️ **Снял бан:** {moderator.mention}",
            color=discord.Color.green(),
            timestamp=utc_now(),
        )
        await self.safe_send_log("moderation", embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogsCog(bot))  # type: ignore[arg-type]
