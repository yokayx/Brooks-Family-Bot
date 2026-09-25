from __future__ import annotations

import re

from discord import Member

from bot.config import FAMILY_NAME
from bot.roster.names import extract_name

# Имя уже с семейным тегом: Klyde Brooks, Klyde_Brooks
_FAMILY_SUFFIX_RE = re.compile(rf"(?:^|[\s._\-]){re.escape(FAMILY_NAME)}$", re.IGNORECASE)


def member_game_name(member: Member) -> str:
    """Игровой тег из ника с семьёй: `Klyde Brooks`.

    Тег — содержимое первых `[]` латиницей или, если скобок нет, часть ника
    до первой `|`. Не вытащился — как в составе, `НИКНЕЙМ ПО ФОРМЕ…`.
    """
    name = extract_name(member.nick or member.display_name)
    if _FAMILY_SUFFIX_RE.search(name):
        return name
    return f"{name} {FAMILY_NAME}"


def participant_line(index: int, member: Member, static: str | None = None) -> str:
    """Строка сбора: `1. Klyde Brooks | Статик`."""
    line = f"{index}. {member_game_name(member)}"
    if static:
        return f"{line} | {static}"
    return line
