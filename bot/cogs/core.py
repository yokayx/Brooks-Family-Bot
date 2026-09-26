from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import OWNER_CHANNEL_ID, ROSTER_CHANNEL_ID, VZP_CHANNEL_ID
from bot.roster.manager import is_leader

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
        synced = await self._sync_guild()
        if synced is None:
            log.error("cannot sync commands: guild not resolved")
            return
        log.info("synced %s guild commands", synced)

    async def _sync_guild(self) -> int | None:
        """Пересинхронизировать команды на нашем сервере. None = сервер не нашли."""
        guild_id = await self._resolve_guild_id()
        if guild_id is None:
            return None
        guild_obj = discord.Object(id=guild_id)
        self.bot.tree.copy_global_to(guild=guild_obj)
        synced = await self.bot.tree.sync(guild=guild_obj)
        self._synced = True
        return len(synced)

    @app_commands.command(name="синк", description="Пересинхронизировать слэш-команды")
    async def sync_now(self, interaction: discord.Interaction) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None or not is_leader(member):
            await interaction.response.send_message("Нет прав.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        synced = await self._sync_guild()
        if synced is None:
            await interaction.followup.send("Не удалось определить сервер.", ephemeral=True)
            return
        await interaction.followup.send(f"Синк: {synced} команд.", ephemeral=True)

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
