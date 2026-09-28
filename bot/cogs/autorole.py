from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot.config import JOIN_ROLE_ID, ROSTER_CHANNEL_ID

if TYPE_CHECKING:
    from bot.main import BrooksBot

log = logging.getLogger("brooks.autorole")


class AutoRoleCog(commands.Cog, name="AutoRole"):
    """Роль при заходе на сервер: выдаём сразу, как человек зашёл."""

    def __init__(self, bot: BrooksBot) -> None:
        self.bot = bot

    def _is_our_guild(self, guild: discord.Guild | None) -> bool:
        if guild is None:
            return False
        channel = self.bot.get_channel(ROSTER_CHANNEL_ID)
        if isinstance(channel, discord.abc.GuildChannel):
            return channel.guild.id == guild.id
        return True

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        if not self._is_our_guild(member.guild):
            return

        role = member.guild.get_role(JOIN_ROLE_ID)
        if role is None:
            log.error("роль при входе %s не найдена на сервере", JOIN_ROLE_ID)
            return

        try:
            await member.add_roles(role, reason="Автовыдача роли при входе")
        except discord.Forbidden:
            log.error(
                "нет прав выдать роль %s: подними роль бота выше и дай «Управление ролями»",
                JOIN_ROLE_ID,
            )
        except discord.HTTPException:
            log.exception("не выдали роль %s участнику %s", JOIN_ROLE_ID, member.id)
        else:
            log.info("выдана роль %s участнику %s", JOIN_ROLE_ID, member.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoRoleCog(bot))  # type: ignore[arg-type]
