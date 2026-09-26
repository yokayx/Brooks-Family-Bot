from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from bot.cogs.autorole import AutoRoleCog
from bot.config import JOIN_ROLE_ID


def _member(*, bot_member: bool = False) -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = JOIN_ROLE_ID
    guild = MagicMock(spec=discord.Guild)
    guild.id = 1
    guild.get_role.return_value = role
    member = MagicMock(spec=discord.Member)
    member.id = 42
    member.bot = bot_member
    member.guild = guild
    member.add_roles = AsyncMock()
    return member


async def test_join_role_is_granted() -> None:
    cog = AutoRoleCog.__new__(AutoRoleCog)
    cog.bot = SimpleNamespace(get_channel=lambda channel_id: None)

    member = _member()
    await cog.on_member_join(member)

    member.add_roles.assert_awaited_once()
    member.guild.get_role.assert_called_once_with(JOIN_ROLE_ID)


async def test_bots_are_skipped() -> None:
    cog = AutoRoleCog.__new__(AutoRoleCog)
    cog.bot = SimpleNamespace(get_channel=lambda channel_id: None)

    member = _member(bot_member=True)
    await cog.on_member_join(member)

    member.add_roles.assert_not_awaited()


async def test_missing_role_is_skipped() -> None:
    """Роли нет на сервере — бот не падает."""
    cog = AutoRoleCog.__new__(AutoRoleCog)
    cog.bot = SimpleNamespace(get_channel=lambda channel_id: None)

    member = _member()
    member.guild.get_role.return_value = None
    await cog.on_member_join(member)

    member.add_roles.assert_not_awaited()
