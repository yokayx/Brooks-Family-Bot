from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands, tasks

from bot.config import (
    LOG_AUDIT_CHANNEL_ID,
    LOG_INVITE_CHANNEL_ID,
    LOG_MEMBER_CHANNEL_ID,
    LOG_MODERATION_CHANNEL_ID,
    LOG_SERVER_CHANNEL_ID,
    LOG_TEXT_CHANNEL_ID,
    LOG_VOICE_CHANNEL_ID,
    ROSTER_CHANNEL_ID,
)

if TYPE_CHECKING:
    from bot.main import BrooksBot

log = logging.getLogger("brooks.logs")
_NO_MENTIONS = discord.AllowedMentions.none()
_MESSAGE_LIMIT = 10_000
_AUDIT_CACHE_LIMIT = 1_000


def format_time_ago(stamp: datetime | None) -> str:
    """`3 дня`, `2 месяца` — как давно создан аккаунт."""
    if stamp is None:
        return "неизвестно"
    delta = datetime.now(UTC) - stamp
    if delta < timedelta(0):
        return "только что"
    return format_years_ago(stamp)


def format_years_ago(stamp: datetime | None) -> str:
    if stamp is None:
        return "неизвестно"
    delta = datetime.now(UTC) - stamp
    years = delta.days // 365
    months = (delta.days % 365) // 30
    if years:
        return f"{years} г."
    if months:
        return f"{months} мес."
    return f"{max(delta.days, 0)} д."


class LogsCog(commands.Cog, name="Logs"):
    """Логи сервера: сообщения, заходы/выходы, модерация, войс, каналы, аудит.

    Порт кога KillaBot: без медиа-хранилища и без своей таблицы инвайтов —
    приглашение определяем по кэшу использований в памяти.
    """

    def __init__(self, bot: BrooksBot) -> None:
        self.bot = bot
        self.invite_cache: dict[int, dict[str, int]] = {}
        self.message_cache: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self.audit_cache: set[int] = set()

    async def cog_load(self) -> None:
        asyncio.create_task(self._cache_invites())
        if not self.audit_poller.is_running():
            self.audit_poller.start()

    async def cog_unload(self) -> None:
        self.audit_poller.cancel()

    # ---------- helpers ----------

    def _guild_id(self) -> int | None:
        channel = self.bot.get_channel(ROSTER_CHANNEL_ID)
        if isinstance(channel, discord.abc.GuildChannel):
            return channel.guild.id
        return None

    def _is_our_guild(self, guild: discord.Guild | None) -> bool:
        if guild is None:
            return False
        known = self._guild_id()
        return known is None or guild.id == known

    async def _send(self, channel_id: int, text: str) -> None:
        if not channel_id:
            return
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except discord.HTTPException:
                log.exception("logs: канал %s недоступен", channel_id)
                return
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            await channel.send(text[:1900], allowed_mentions=_NO_MENTIONS)
        except discord.HTTPException:
            log.exception("logs: не отправили лог в %s", channel_id)

    async def _cache_invites(self) -> None:
        await self.bot.wait_until_ready()
        guild_id = self._guild_id()
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if guild is None:
            return
        try:
            invites = await guild.invites()
        except discord.HTTPException:
            log.exception("logs: не закэшировали инвайты")
            return
        self.invite_cache[guild.id] = {invite.code: invite.uses or 0 for invite in invites}

    async def _detect_used_invite(
        self, guild: discord.Guild
    ) -> tuple[discord.Invite | None, int | None]:
        try:
            invites = await guild.invites()
        except discord.HTTPException:
            log.exception("logs: не получили инвайты при входе")
            return None, None

        previous = self.invite_cache.get(guild.id, {})
        used: discord.Invite | None = None
        inviter_id: int | None = None
        for invite in invites:
            if (invite.uses or 0) > previous.get(invite.code, 0):
                used = invite
                inviter_id = invite.inviter.id if invite.inviter else None
                break

        self.invite_cache[guild.id] = {invite.code: invite.uses or 0 for invite in invites}
        return used, inviter_id

    # ---------- сообщения ----------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not self._is_our_guild(message.guild):
            return

        self.message_cache[message.id] = {
            "author_id": message.author.id,
            "author_name": str(message.author),
            "channel_id": message.channel.id,
            "content": message.content,
            "attachments": [item.url for item in message.attachments],
        }
        while len(self.message_cache) > _MESSAGE_LIMIT:
            self.message_cache.popitem(last=False)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or not self._is_our_guild(message.guild):
            return
        payload = self.message_cache.pop(message.id, None)
        if payload is None:
            payload = {
                "author_id": getattr(message.author, "id", 0),
                "author_name": str(message.author),
                "channel_id": message.channel.id,
                "content": message.content,
                "attachments": [item.url for item in message.attachments],
            }
        text = (
            "**Удалено сообщение**\n"
            f"Канал: <#{payload['channel_id']}>\n"
            f"Автор: <@{payload['author_id']}> ({payload['author_name']})\n"
            f"Текст: {payload['content'] or '—'}"
        )
        if payload["attachments"]:
            text += "\nВложения:\n" + "\n".join(payload["attachments"])
        await self._send(LOG_TEXT_CHANNEL_ID, text)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild is None or before.author.bot:
            return
        if not self._is_our_guild(before.guild) or before.content == after.content:
            return
        await self._send(
            LOG_TEXT_CHANNEL_ID,
            "**Изменено сообщение**\n"
            f"Канал: <#{before.channel.id}>\n"
            f"Автор: {before.author.mention}\n"
            f"Старое: {before.content or '—'}\n"
            f"Новое: {after.content or '—'}",
        )

    # ---------- участники ----------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if not self._is_our_guild(member.guild):
            return
        used, inviter_id = await self._detect_used_invite(member.guild)
        inviter_text = f"<@{inviter_id}>" if inviter_id else "Неизвестно"
        invite_text = f"{used.code} (использован {used.uses} раз)" if used else "Неизвестно"
        await self._send(
            LOG_INVITE_CHANNEL_ID,
            f"{member.mention} ({member.name}) зашёл. ID: {member.id}. "
            f"Аккаунт создан {format_time_ago(member.created_at)} "
            f"({format_years_ago(member.created_at)}). "
            f"Пригласил {inviter_text} по ссылке {invite_text}.",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if not self._is_our_guild(member.guild):
            return
        kick_by = None
        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if entry.target is not None and entry.target.id == member.id:
                    if (datetime.now(UTC) - entry.created_at) < timedelta(seconds=10):
                        kick_by = entry.user.mention if entry.user else "неизвестно"
                    break
        except discord.HTTPException:
            log.exception("logs: не проверили аудит на кик")

        if kick_by:
            await self._send(
                LOG_MODERATION_CHANNEL_ID,
                f"Пользователь {member} ({member.id}) кикнут модератором {kick_by}.",
            )
            return
        await self._send(
            LOG_INVITE_CHANNEL_ID,
            f"{member} ({member.id}) вышел с сервера.",
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if not self._is_our_guild(guild):
            return
        await self._send(LOG_MODERATION_CHANNEL_ID, f"{user} ({user.id}) забанен.")

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        if not self._is_our_guild(guild):
            return
        await self._send(LOG_MODERATION_CHANNEL_ID, f"{user} ({user.id}) разбанен.")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if not self._is_our_guild(after.guild):
            return

        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until is not None:
                stamp = discord.utils.format_dt(after.timed_out_until, style="F")
                await self._send(
                    LOG_MODERATION_CHANNEL_ID,
                    f"{after.mention} получил тайм-аут до {stamp}.",
                )
            else:
                await self._send(LOG_MODERATION_CHANNEL_ID, f"С {after.mention} снят тайм-аут.")

        before_roles = {role.id for role in before.roles}
        after_roles = {role.id for role in after.roles}
        if before_roles != after_roles:
            added = [role.mention for role in after.roles if role.id not in before_roles]
            removed = [role.mention for role in before.roles if role.id not in after_roles]
            await self._send(
                LOG_MEMBER_CHANNEL_ID,
                f"Изменение ролей у {after.mention}. "
                f"Добавлены: {', '.join(added) or '—'}. "
                f"Сняты: {', '.join(removed) or '—'}.",
            )

        if before.display_name != after.display_name:
            await self._send(
                LOG_MODERATION_CHANNEL_ID,
                f"Участник {after.mention} сменил никнейм: "
                f"`{before.display_name}` -> `{after.display_name}`.",
            )

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User) -> None:
        if before.name == after.name:
            return
        guild_id = self._guild_id()
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if guild is None or guild.get_member(after.id) is None:
            return
        await self._send(
            LOG_MEMBER_CHANNEL_ID,
            f"<@{after.id}> сменил username: `{before.name}` -> `{after.name}`.",
        )

    # ---------- войс ----------

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if not self._is_our_guild(member.guild):
            return
        if before.channel != after.channel:
            if before.channel is None and after.channel is not None:
                text = f"{member.mention} вошёл в {after.channel.mention}."
            elif before.channel is not None and after.channel is None:
                text = f"{member.mention} вышел из {before.channel.mention}."
            else:
                text = (
                    f"{member.mention} переместился из {before.channel.mention} "
                    f"в {after.channel.mention}."
                )
            await self._send(LOG_VOICE_CHANNEL_ID, text)
        if before.self_mute != after.self_mute:
            state = "включил" if after.self_mute else "выключил"
            await self._send(LOG_VOICE_CHANNEL_ID, f"{member.mention} {state} микрофонный мут.")
        if before.self_deaf != after.self_deaf:
            state = "выключил" if after.self_deaf else "включил"
            await self._send(LOG_VOICE_CHANNEL_ID, f"{member.mention} {state} звук.")

    # ---------- каналы ----------

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        if not self._is_our_guild(channel.guild):
            return
        mention = getattr(channel, "mention", None) or channel.name
        await self._send(LOG_SERVER_CHANNEL_ID, f"Создан канал: {mention}")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if not self._is_our_guild(channel.guild):
            return
        await self._send(LOG_SERVER_CHANNEL_ID, f"Удалён канал: {channel.name} ({channel.id})")

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        if not self._is_our_guild(after.guild):
            return
        if before.overwrites != after.overwrites:
            await self._send(LOG_SERVER_CHANNEL_ID, f"Изменены права доступа канала {after.name}.")

    # ---------- аудит ----------

    @tasks.loop(seconds=30)
    async def audit_poller(self) -> None:
        if not LOG_AUDIT_CHANNEL_ID:
            return
        guild_id = self._guild_id()
        guild = self.bot.get_guild(guild_id) if guild_id else None
        if guild is None:
            return
        try:
            entries = [entry async for entry in guild.audit_logs(limit=20)]
        except discord.HTTPException:
            log.exception("logs: не опросили аудит")
            return

        for entry in reversed(entries):
            if entry.id in self.audit_cache:
                continue
            self.audit_cache.add(entry.id)
            target = (
                getattr(entry.target, "mention", None)
                or getattr(entry.target, "name", None)
                or str(entry.target)
            )
            actor = entry.user.mention if entry.user else "Неизвестно"
            await self._send(
                LOG_AUDIT_CHANNEL_ID,
                f"**Audit** | {entry.action.name} | Исполнитель: {actor} | "
                f"Цель: {target} | Причина: {entry.reason or '—'}",
            )

        if len(self.audit_cache) > _AUDIT_CACHE_LIMIT:
            self.audit_cache = set(list(self.audit_cache)[-500:])

    @audit_poller.before_loop
    async def before_audit_poller(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogsCog(bot))  # type: ignore[arg-type]
