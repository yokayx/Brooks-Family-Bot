from __future__ import annotations

import re

from discord import Member

from bot.config import FALLBACK_NICK, FAMILY_NAME
from bot.roster.names import extract_name

# Имя уже с семейным тегом: Klyde Brooks, Klyde_Brooks
_FAMILY_SUFFIX_RE = re.compile(rf"(?:^|[\s._\-]){re.escape(FAMILY_NAME)}$", re.IGNORECASE)


def member_game_name(member: Member) -> str:
    """Игровой тег с семьёй: `Klyde Brooks`.

    Пустая строка, если тег из ника не вытащился: в сборах идентификатор —
    тег участника (`<@id>`), а не его никнейм.
    """
    name = extract_name(member.nick or member.display_name)
    if not name or name == FALLBACK_NICK:
        return ""
    if _FAMILY_SUFFIX_RE.search(name):
        return name
    return f"{name} {FAMILY_NAME}"


def participant_line(user_id: int, member: Member | None) -> str:
    """Строка участника сбора: `<@id> | Klyde Brooks`.

    Тег участника — всегда; игровой тег из ника — когда он вытащился.
    """
    tag = f"<@{user_id}>"
    name = member_game_name(member) if member is not None else ""
    return f"{tag} | {name}" if name else tag
