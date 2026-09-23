from discord import Member

from bot.config import FAMILY_NAME
from bot.roster.names import extract_name


def member_game_name(member: Member) -> str:
    nick = extract_name(member.nick or member.display_name)
    return f"{nick} {FAMILY_NAME}"
