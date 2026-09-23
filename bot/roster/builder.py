from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bot.config import (
    DISCORD_MESSAGE_LIMIT,
    FAMILY_NAME,
    RANK_ROLES,
)
from bot.roster.names import extract_name


class RoleLike(Protocol):
    id: int


class MemberLike(Protocol):
    id: int
    bot: bool
    nick: str | None
    display_name: str
    roles: list[RoleLike]


@dataclass(frozen=True)
class RosterPayload:
    messages: tuple[str, ...]
    unique_count: int
    member_ids: frozenset[int]


def _profile_name(member: MemberLike) -> str:
    return extract_name(member.nick or member.display_name)


def _split_section(title: str, lines: list[str], limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    heading = f"## {title}"
    chunks: list[str] = []
    current: list[str] = [heading]
    size = len(heading)

    for line in lines:
        extra = 1 + len(line)  # newline + line
        if current and size + extra > limit:
            chunks.append("\n".join(current))
            current = [heading, line]
            size = len(heading) + extra
        else:
            current.append(line)
            size += extra

    if len(current) > 1:
        chunks.append("\n".join(current))
    return chunks


def build_roster(
    members: list[MemberLike],
    ranks: tuple[tuple[int, str], ...] = RANK_ROLES,
) -> RosterPayload:
    sections: dict[int, list[tuple[str, int]]] = {role_id: [] for role_id, _ in ranks}
    unique: set[int] = set()

    for member in members:
        if member.bot:
            continue
        role_ids = {role.id for role in member.roles}
        name = _profile_name(member)
        in_family = False
        for role_id, _title in ranks:
            if role_id in role_ids:
                sections[role_id].append((name, member.id))
                in_family = True
        if in_family:
            unique.add(member.id)

    texts: list[str] = [f"# Состав {FAMILY_NAME}\n## Численность: {len(unique)}"]

    for role_id, title in ranks:
        people = sections[role_id]
        if not people:
            continue
        people.sort(key=lambda item: (item[0].casefold(), item[1]))
        lines = [f"<@{user_id}> | {name}" for name, user_id in people]
        texts.extend(_split_section(title, lines))

    return RosterPayload(tuple(texts), len(unique), frozenset(unique))
