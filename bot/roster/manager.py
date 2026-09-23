from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from bot.config import (
    ERROR_CHANNEL_TEXT,
    LEADERSHIP_ROLE_IDS,
    MAX_SEND_ATTEMPTS,
    OWNER_CHANNEL_ID,
    PLACEHOLDER,
    RANK_ROLE_IDS,
    RANK_ROLES,
    ROSTER_CHANNEL_ID,
    SEND_GAP_SECONDS,
)
from bot.roster.builder import RosterPayload, build_roster
from bot.roster.state import load_state, save_state

if TYPE_CHECKING:
    from discord.ext.commands import Bot

log = logging.getLogger("brooks.roster")

_ALLOWED_EDIT = discord.AllowedMentions(everyone=False, users=True, roles=False, replied_user=False)
_ALLOWED_NONE = discord.AllowedMentions.none()


class RosterManager:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self._lock = asyncio.Lock()
        self._dirty = False
        self._syncing = False
        self.fail_state = False
        self.message_ids: list[int] = []
        self.tracked_members: frozenset[int] = frozenset()

    @property
    def syncing(self) -> bool:
        return self._syncing

    async def load(self) -> None:
        self.fail_state, self.message_ids = await load_state()
        log.info("roster state: fail=%s messages=%s", self.fail_state, self.message_ids)

    def is_roster_message(self, message_id: int) -> bool:
        return message_id in self.message_ids

    def was_in_roster(self, user_id: int) -> bool:
        return user_id in self.tracked_members

    async def notify_changed(self, reason: str) -> None:
        if self.fail_state:
            log.info("skip roster update (%s): fail-state, нужен /refresh", reason)
            return
        self._dirty = True
        if self._lock.locked():
            return
        async with self._lock:
            while self._dirty and not self.fail_state:
                self._dirty = False
                await self._sync(reason, force_resend=False)

    async def midnight_resend(self) -> None:
        if self.fail_state:
            log.info("midnight skipped: fail-state")
            return
        async with self._lock:
            self._dirty = False
            await self._sync("midnight", force_resend=True)

    async def force_refresh(self, reason: str = "refresh") -> str:
        async with self._lock:
            self.fail_state = False
            self._dirty = False
            return await self._sync(reason, force_resend=True)

    async def handle_foreign_message(self, message: discord.Message) -> None:
        if self._syncing or self.fail_state:
            return
        if message.channel.id != ROSTER_CHANNEL_ID:
            return
        if message.author.id == self.bot.user.id:  # type: ignore[union-attr]
            return
        try:
            await message.delete()
            log.info("deleted extra message %s in roster channel", message.id)
        except discord.HTTPException:
            log.warning("could not delete extra message, full resend")
            await self.notify_changed("foreign_message")

    async def _sync(self, reason: str, *, force_resend: bool) -> str:
        channel = await self._roster_channel()
        if channel is None:
            return "no_channel"

        guild = channel.guild
        if not guild.chunked:
            await guild.chunk()

        payload = build_roster(list(guild.members), RANK_ROLES)
        log.info(
            "rebuild (%s): %s unique, %s messages, force=%s",
            reason,
            payload.unique_count,
            len(payload.messages),
            force_resend,
        )

        if not force_resend:
            edited = await self._try_edit(channel, payload)
            if edited:
                self.tracked_members = payload.member_ids
                return "edited"

        result = await self._full_send(channel, payload)
        if result == "sent":
            self.tracked_members = payload.member_ids
        return result

    async def _try_edit(self, channel: discord.TextChannel, payload: RosterPayload) -> bool:
        if len(self.message_ids) != len(payload.messages):
            return False
        if not await self._ids_intact(channel):
            return False

        self._syncing = True
        try:
            for message_id, text in zip(self.message_ids, payload.messages, strict=True):
                try:
                    message = await channel.fetch_message(message_id)
                except discord.NotFound:
                    return False
                if message.content != text:
                    await message.edit(content=text, allowed_mentions=_ALLOWED_EDIT)
                    await asyncio.sleep(SEND_GAP_SECONDS)
            if await self._verify(channel, payload.messages):
                await save_state(fail_state=False, message_ids=self.message_ids)
                return True
        except discord.HTTPException:
            log.exception("edit-in-place failed")
            return False
        finally:
            self._syncing = False
        return False

    async def _full_send(self, channel: discord.TextChannel, payload: RosterPayload) -> str:
        last_error: Exception | str = "verify_failed"
        self._syncing = True
        try:
            for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
                try:
                    await self._wipe(channel)
                    sent: list[discord.Message] = []
                    for _ in payload.messages:
                        msg = await channel.send(PLACEHOLDER, allowed_mentions=_ALLOWED_NONE)
                        sent.append(msg)
                        await asyncio.sleep(SEND_GAP_SECONDS)
                    for msg, text in zip(sent, payload.messages, strict=True):
                        await msg.edit(content=text, allowed_mentions=_ALLOWED_EDIT)
                        await asyncio.sleep(SEND_GAP_SECONDS)
                    if await self._verify(channel, payload.messages):
                        self.message_ids = [m.id for m in sent]
                        self.fail_state = False
                        await save_state(fail_state=False, message_ids=self.message_ids)
                        log.info("roster sent on attempt %s", attempt)
                        return "sent"
                    last_error = "verify_failed"
                    log.warning("roster verify failed, attempt %s/%s", attempt, MAX_SEND_ATTEMPTS)
                except Exception as exc:
                    last_error = exc
                    log.exception("roster send failed, attempt %s/%s", attempt, MAX_SEND_ATTEMPTS)
                await asyncio.sleep(1)

            await self._enter_fail_state(channel, last_error)
            return "failed"
        finally:
            self._syncing = False

    async def _enter_fail_state(self, channel: discord.TextChannel, error: Exception | str) -> None:
        self.fail_state = True
        self.message_ids = []
        await save_state(fail_state=True, message_ids=[])
        try:
            await self._wipe(channel)
            await channel.send(ERROR_CHANNEL_TEXT, allowed_mentions=_ALLOWED_NONE)
        except discord.HTTPException:
            log.exception("could not post fail message in roster channel")
        await self._notify_owners(error)

    async def _notify_owners(self, error: Exception | str) -> None:
        channel = self.bot.get_channel(OWNER_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(OWNER_CHANNEL_ID)
            except discord.HTTPException:
                log.exception("owner channel unavailable")
                return
        if not isinstance(channel, discord.TextChannel):
            return
        tags = " ".join(f"<@&{role_id}>" for role_id in LEADERSHIP_ROLE_IDS)
        text = f"{tags}\n{ERROR_CHANNEL_TEXT}.\nПричина: `{error}`"
        try:
            await channel.send(text, allowed_mentions=discord.AllowedMentions(roles=True))
        except discord.HTTPException:
            log.exception("failed to notify owners")

    async def _verify(self, channel: discord.TextChannel, expected: tuple[str, ...]) -> bool:
        await asyncio.sleep(0.5)
        messages = [m async for m in channel.history(limit=100, oldest_first=True)]
        if len(messages) != len(expected):
            return False
        return all(msg.content == text for msg, text in zip(messages, expected, strict=True))

    async def _ids_intact(self, channel: discord.TextChannel) -> bool:
        messages = [m async for m in channel.history(limit=100, oldest_first=True)]
        return [m.id for m in messages] == self.message_ids

    async def _wipe(self, channel: discord.TextChannel) -> None:
        for _ in range(30):
            batch = [m async for m in channel.history(limit=100)]
            if not batch:
                return
            try:
                if len(batch) == 1:
                    await batch[0].delete()
                else:
                    await channel.delete_messages(batch)
            except discord.HTTPException:
                for msg in batch:
                    try:
                        await msg.delete()
                    except discord.HTTPException:
                        log.warning("could not delete message %s", msg.id)
                    await asyncio.sleep(0.3)
            await asyncio.sleep(0.3)

    async def _roster_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(ROSTER_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(ROSTER_CHANNEL_ID)
            except discord.HTTPException:
                log.exception("roster channel not found")
                return None
        if not isinstance(channel, discord.TextChannel):
            log.error("roster channel is not a text channel")
            return None
        return channel


def member_affects_roster(before: discord.Member, after: discord.Member) -> bool:
    before_ids = {role.id for role in before.roles}
    after_ids = {role.id for role in after.roles}
    rank_changed = bool((before_ids ^ after_ids) & RANK_ROLE_IDS)
    nick_changed = (before.nick != after.nick) or (before.display_name != after.display_name)
    in_family = bool(after_ids & RANK_ROLE_IDS) or bool(before_ids & RANK_ROLE_IDS)
    return rank_changed or (nick_changed and in_family)


def is_leader(member: discord.Member) -> bool:
    return any(role.id in LEADERSHIP_ROLE_IDS for role in member.roles)
