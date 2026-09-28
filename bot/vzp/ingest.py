"""Приём данных о войнах ВЗП от внешнего инструмента.

Канонические ключи — как у публичного API vzp-launcher.pro (их ждут
`bot.vzp.format` и `bot.vzp.filter`), но с запасом по синонимам: инструмент
может отдавать поля в своём виде.
"""

from __future__ import annotations

from typing import Any

_WAR_ALIASES = {
    "war_id": "id",
    "uuid": "id",
    "server": "server_name",
    "attacker": "attacker_name",
    "defender": "defender_name",
    "winner": "winner_side",
    "point": "territory",
    "map": "map_name",
    "players": "participants",
    "score_attacker": "attacker_score",
    "score_defender": "defender_score",
}

_PLAYER_ALIASES = {
    "name": "player_name",
    "nickname": "player_name",
    "nick": "player_name",
    "accuracy": "hit_percent",
    "hs": "headshot_percent",
    "headshots": "headshot_percent",
    "side": "family_side",
    "team": "family_side",
}


def _remap(data: dict, aliases: dict[str, str]) -> dict:
    result = dict(data)
    for alias, canonical in aliases.items():
        if alias not in result:
            continue
        value = result.pop(alias)
        if canonical not in result:
            result[canonical] = value
    return result


def normalize_war(data: Any) -> dict | None:
    """Одна война в канонических ключах."""
    if not isinstance(data, dict):
        return None

    war = _remap(data, _WAR_ALIASES)
    war["id"] = str(war.get("id") or "").strip()

    people = war.get("participants")
    if isinstance(people, list):
        war["participants"] = [
            _remap(person, _PLAYER_ALIASES) for person in people if isinstance(person, dict)
        ]
    return war


def extract_wars(payload: Any) -> list[dict]:
    """Из ответа инструмента — список войн. Отдаём то, что похоже на войну."""
    if isinstance(payload, list):
        raw: list[Any] = payload
    elif isinstance(payload, dict):
        nested = payload.get("wars") or payload.get("data") or payload.get("results")
        if isinstance(nested, list):
            raw = nested
        elif isinstance(payload.get("war"), dict):
            raw = [payload["war"]]
        else:
            raw = [payload]
    else:
        return []

    wars: list[dict] = []
    for item in raw:
        war = normalize_war(item)
        if war is not None and (war.get("id") or war.get("attacker_name")):
            wars.append(war)
    return wars
