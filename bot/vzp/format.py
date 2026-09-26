from __future__ import annotations

import discord

from bot.config import FAMILY_NAME
from bot.vzp.dt import fmt_dt as _fmt_dt
from bot.vzp.filter import brooks_side, brooks_won

_WIN = discord.Color.from_rgb(46, 204, 113)
_LOSS = discord.Color.from_rgb(231, 76, 60)
_DRAW = discord.Color.from_rgb(149, 165, 166)


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


def _num(value: object) -> str:
    """17.9 → `17.9`, 20.0 → `20`."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:g}"


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
        hs = person.get("headshot_percent")
        stats = f"{_num(acc)}%" if acc is not None else "—"
        if hs is not None:
            stats += f" / {_num(hs)}%HS"
        rows.append(f"{kills} {dmg} - {stats} - {name}")
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
        title = f"Победа · {role} · {FAMILY_NAME}"
        color = _WIN
    elif won is False:
        title = f"Поражение · {role} · {FAMILY_NAME}"
        color = _LOSS
    else:
        title = f"Итог · {role} · {FAMILY_NAME}"
        color = _DRAW

    war_id = str(war.get("id") or "").strip()
    embed = discord.Embed(
        title=title,
        description=(
            f"**{role}** {FAMILY_NAME} vs **{enemy}**\n"
            f"Счёт **{us} : {them}**"
        ),
        color=color,
        url=f"https://vzp-launcher.pro/vzp?war={war_id}" if war_id else None,
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
    return embed
