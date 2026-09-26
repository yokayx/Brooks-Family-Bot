from __future__ import annotations

from discord import Member

from bot.roster.names import extract_name, with_family


def member_game_name(member: Member) -> str:
    """Игровой тег из ника с семьёй: `Klyde Brooks`.

    Тег — содержимое первых `[]` латиницей или, если скобок нет, часть ника
    до первой `|`. Не вытащился — `ник по форме`, без семьи.
    """
    return with_family(extract_name(member.nick or member.display_name))


def participant_line(index: int, member: Member, static: str | None = None) -> str:
    """Строка сбора со статиком: `1. Klyde Brooks | Статик`."""
    line = f"{index}. {member_game_name(member)}"
    if static:
        return f"{line} | {static}"
    return line


def participant_tag_line(index: int, user_id: int) -> str:
    """Строка сбора без статика: `1. <@id>` — Discord сам покажет ник."""
    return f"{index}. <@{user_id}>"
