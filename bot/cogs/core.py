from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.config import OWNER_CHANNEL_ID, ROSTER_CHANNEL_ID, VZP_CHANNEL_ID

log = logging.getLogger("brooks.core")


class CoreCog(commands.Cog, name="Core"):
    """Служебное: ready, синхронизация слэш-команд. Не бизнес-логика семьи."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._synced = False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        log.info("logged in as %s", self.bot.user)
        if self._synced:
            return
        guild_id = await self._resolve_guild_id()
        if guild_id is None:
            log.error("cannot sync commands: guild not resolved")
            return
        guild_obj = discord.Object(id=guild_id)
        self.bot.tree.copy_global_to(guild=guild_obj)
        synced = await self.bot.tree.sync(guild=guild_obj)
        self._synced = True
        log.info("synced %s guild commands for %s", len(synced), guild_id)

    async def _resolve_guild_id(self) -> int | None:
        channel = (
            self.bot.get_channel(ROSTER_CHANNEL_ID)
            or self.bot.get_channel(VZP_CHANNEL_ID)
            or self.bot.get_channel(OWNER_CHANNEL_ID)
        )
        if isinstance(channel, discord.abc.GuildChannel):
            return channel.guild.id
        try:
            fetched = await self.bot.fetch_channel(ROSTER_CHANNEL_ID)
        except discord.HTTPException:
            log.exception("cannot resolve guild from roster channel")
            return None
        if isinstance(fetched, discord.abc.GuildChannel):
            return fetched.guild.id
        return None


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CoreCog(bot))
