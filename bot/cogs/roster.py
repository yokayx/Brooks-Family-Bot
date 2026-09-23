from __future__ import annotations

import logging
from datetime import time
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.config import MOSCOW_TZ, OWNER_CHANNEL_ID, RANK_ROLE_IDS, ROSTER_CHANNEL_ID
from bot.roster.manager import RosterManager, is_leader, member_affects_roster

log = logging.getLogger("brooks.roster.cog")


class RosterCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.manager = RosterManager(bot)
        self._ready = False

    async def cog_load(self) -> None:
        await self.manager.load()
        if not self.midnight_resend.is_running():
            self.midnight_resend.start()

    async def cog_unload(self) -> None:
        self.midnight_resend.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._ready:
            return
        self._ready = True
        log.info("roster cog ready as %s", self.bot.user)
        guild_id = await self._resolve_guild_id()
        if guild_id is not None:
            guild_obj = discord.Object(id=guild_id)
            self.bot.tree.copy_global_to(guild=guild_obj)
            synced = await self.bot.tree.sync(guild=guild_obj)
            log.info("synced %s guild commands", len(synced))
        await self.manager.notify_changed("startup")

    @tasks.loop(time=time(hour=0, minute=0, tzinfo=ZoneInfo(MOSCOW_TZ)))
    async def midnight_resend(self) -> None:
        log.info("00:00 MSK — переотправка состава")
        await self.manager.midnight_resend()

    @midnight_resend.before_loop
    async def before_midnight(self) -> None:
        await self.bot.wait_until_ready()

    @app_commands.command(name="refresh", description="Пересобрать состав (руководство)")
    async def refresh(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member) or not is_leader(member):
            await interaction.response.send_message("Нет прав.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        result = await self.manager.force_refresh("slash_refresh")
        labels = {
            "sent": "Состав отправлен заново.",
            "edited": "Состав обновлён.",
            "failed": "Не удалось отправить состав (3 попытки). Смотри owner-чат.",
            "no_channel": "Канал состава недоступен.",
        }
        await interaction.followup.send(labels.get(result, result), ephemeral=True)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.guild.id != self._guild_id():
            return
        if member_affects_roster(before, after):
            await self.manager.notify_changed("member_update")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.guild.id != self._guild_id():
            return
        if any(role.id in RANK_ROLE_IDS for role in member.roles):
            await self.manager.notify_changed("join")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.guild.id != self._guild_id():
            return
        roles = getattr(member, "roles", [])
        if any(role.id in RANK_ROLE_IDS for role in roles) or self.manager.was_in_roster(member.id):
            await self.manager.notify_changed("leave")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.channel.id != ROSTER_CHANNEL_ID:
            return
        await self.manager.handle_foreign_message(message)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.channel_id != ROSTER_CHANNEL_ID:
            return
        if self.manager.syncing or self.manager.fail_state:
            return
        if self.manager.is_roster_message(payload.message_id):
            await self.manager.notify_changed("message_deleted")

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.channel_id != ROSTER_CHANNEL_ID:
            return
        if self.manager.syncing or self.manager.fail_state:
            return
        if not self.manager.is_roster_message(payload.message_id):
            return
        if "content" not in payload.data:
            return
        await self.manager.notify_changed("message_edited")

    def _guild_id(self) -> int | None:
        channel = self.bot.get_channel(ROSTER_CHANNEL_ID) or self.bot.get_channel(OWNER_CHANNEL_ID)
        if isinstance(channel, discord.abc.GuildChannel):
            return channel.guild.id
        return None

    async def _resolve_guild_id(self) -> int | None:
        guild_id = self._guild_id()
        if guild_id is not None:
            return guild_id
        try:
            channel = await self.bot.fetch_channel(ROSTER_CHANNEL_ID)
        except discord.HTTPException:
            log.exception("cannot resolve guild from roster channel")
            return None
        if isinstance(channel, discord.abc.GuildChannel):
            return channel.guild.id
        return None
