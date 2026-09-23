from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import discord

from bot.config import FAMILY_NAME, MOSCOW_TZ, VZP_SOURCE_NOTE
from bot.vzp.filter import brooks_side, brooks_won

_MSK = ZoneInfo(MOSCOW_TZ)
_WIN = discord.Color.from_rgb(46, 204, 113)
_LOSS = discord.Color.from_rgb(231, 76, 60)
_DRAW = discord.Color.from_rgb(149, 165, 166)


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_MSK)


def _fmt_dt(value: object) -> str:
    dt = _parse_dt(value)
    if dt is None:
        return "—"
    return dt.strftime("%d.%m %H:%M")


def _opponent(war: dict, side: str) -> str:
    if side == "attacker":
        return str(war.get("defender_name") or "—")
    return str(war.get("attacker_name") or "—")


def _our_score(war: dict, side: str) -> tuple[int, int]:
    atk = int(war.get("attacker_score") or 0)
    dfn = int(war.get("defender_score") or 0)
    if side == "attacker":
        return atk, dfn
    return dfn, atk


def _lines(people: list[dict], *, limit: int = 12) -> str:
    if not people:
        return "нет данных"
    ordered = sorted(
        people,
        key=lambda p: (-int(p.get("kills") or 0), -int(p.get("damage") or 0)),
    )
    rows: list[str] = []
    for person in ordered[:limit]:
        name = str(person.get("player_name") or "—")
        kills = int(person.get("kills") or 0)
        dmg = int(person.get("damage") or 0)
        acc = person.get("hit_percent")
        acc_s = f" · {acc}%" if acc is not None else ""
        rows.append(f"`{kills:>2}` `{dmg:>4}`{acc_s}  {name}")
    extra = len(ordered) - limit
    if extra > 0:
        rows.append(f"… ещё {extra}")
    return "\n".join(rows)


def build_result_embed(war: dict) -> discord.Embed:
    side = brooks_side(war) or "attacker"
    won = brooks_won(war)
    us, them = _our_score(war, side)
    role = "ATK" if side == "attacker" else "DEF"
    enemy = _opponent(war, side)
    if won is True:
        title = f"Победа · {FAMILY_NAME}"
        color = _WIN
    elif won is False:
        title = f"Поражение · {FAMILY_NAME}"
        color = _LOSS
    else:
        title = f"Итог · {FAMILY_NAME}"
        color = _DRAW

    embed = discord.Embed(
        title=title,
        description=(
            f"**{role}** {FAMILY_NAME} vs **{enemy}**\n"
            f"Счёт **{us} : {them}**"
        ),
        color=color,
        url=f"https://vzp-launcher.pro/family/{FAMILY_NAME}",
    )
    embed.add_field(name="Точка", value=str(war.get("territory") or "—"), inline=True)
    embed.add_field(name="Карта", value=str(war.get("map_name") or "—"), inline=True)
    embed.add_field(name="Сервер", value=str(war.get("server_name") or "—"), inline=True)
    embed.add_field(
        name="Время МСК",
        value=f"{_fmt_dt(war.get('started_at'))} → {_fmt_dt(war.get('ended_at'))}",
        inline=False,
    )

    people = list(war.get("participants") or [])
    ours = [p for p in people if p.get("family_side") == side]
    foes = [p for p in people if p.get("family_side") != side]
    embed.add_field(
        name=f"{FAMILY_NAME} ({len(ours)})",
        value=_lines(ours)[:1024],
        inline=False,
    )
    embed.add_field(
        name=f"{enemy} ({len(foes)})",
        value=_lines(foes)[:1024],
        inline=False,
    )
    skill = war.get("match_skill_tier")
    footer = VZP_SOURCE_NOTE
    if skill:
        footer = f"{skill} · {footer}"
    embed.set_footer(text=footer)
    ended = _parse_dt(war.get("ended_at"))
    if ended is not None:
        embed.timestamp = ended
    return embed
