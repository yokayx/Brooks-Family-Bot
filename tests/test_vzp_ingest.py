import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from bot.vzp.ingest import extract_wars, normalize_war


def _war() -> dict:
    return {
        "id": "76a842d5-f43b-4781-9a94-59bdea0ae20f",
        "server_name": "RICHMAN",
        "attacker_name": "Brooks",
        "defender_name": "Vagos",
        "winner_side": "attacker",
        "status": "finished",
        "attacker_score": 3,
        "defender_score": 1,
        "territory": "Точка 5",
        "map_name": "Paleto",
        "started_at": "2026-09-26T18:00:00Z",
        "ended_at": "2026-09-26T18:20:00Z",
        "participants": [
            {
                "player_name": "Klyde_Brooks",
                "family_side": "attacker",
                "kills": 3,
                "damage": 900,
                "hit_percent": 26,
                "headshot_percent": 5.6,
            }
        ],
    }


def test_normalize_aliases() -> None:
    war = normalize_war(
        {
            "war_id": "w-1",
            "server": "RICHMAN",
            "attacker": "Brooks",
            "defender": "Vagos",
            "winner": "attacker",
            "point": "Точка 5",
            "map": "Paleto",
            "players": [{"nick": "Klyde", "side": "attacker", "accuracy": 30, "hs": 10}],
        }
    )
    assert war is not None
    assert war["id"] == "w-1"
    assert war["server_name"] == "RICHMAN"
    assert war["attacker_name"] == "Brooks"
    assert war["defender_name"] == "Vagos"
    assert war["winner_side"] == "attacker"
    assert war["territory"] == "Точка 5"
    assert war["map_name"] == "Paleto"
    assert war["participants"][0]["player_name"] == "Klyde"
    assert war["participants"][0]["hit_percent"] == 30
    assert war["participants"][0]["headshot_percent"] == 10


def test_extract_forms() -> None:
    war = _war()
    assert len(extract_wars([war])) == 1
    assert len(extract_wars({"wars": [war]})) == 1
    assert len(extract_wars({"war": war})) == 1
    assert len(extract_wars(war)) == 1
    assert extract_wars("мусор") == []
    assert extract_wars({}) == []


async def test_ingest_message_posts_result(monkeypatch) -> None:
    """JSON в канале приёма -> итог в канал ВЗП."""
    import bot.cogs.vzp as vzp_module
    from bot.cogs.vzp import VzpCog

    war = _war()
    cog = VzpCog.__new__(VzpCog)

    sent: list[discord.Embed] = []
    channel = MagicMock(spec=discord.TextChannel)

    async def fake_send(embed: discord.Embed, **_kwargs: object) -> SimpleNamespace:
        sent.append(embed)
        return SimpleNamespace(id=555)

    channel.send = fake_send

    async def fake_channel() -> MagicMock:
        return channel

    cog._channel = fake_channel
    monkeypatch.setattr(vzp_module, "VZP_INGEST_CHANNEL_ID", 777)
    monkeypatch.setattr(vzp_module, "already_posted", AsyncMock(return_value=False))
    monkeypatch.setattr(vzp_module, "mark_posted", AsyncMock())
    monkeypatch.setattr(vzp_module, "defense_noticed", AsyncMock(return_value=True))
    monkeypatch.setattr(vzp_module, "mark_defense", AsyncMock())

    message = SimpleNamespace(
        id=1,
        channel=SimpleNamespace(id=777),
        content=json.dumps({"wars": [war]}),
        attachments=[],
        add_reaction=AsyncMock(),
    )

    await cog.on_message(message)

    assert len(sent) == 1
    assert sent[0].title.startswith("Победа")
    assert "Brooks" in sent[0].description


async def test_ingest_ignores_other_channels(monkeypatch) -> None:
    import bot.cogs.vzp as vzp_module
    from bot.cogs.vzp import VzpCog

    cog = VzpCog.__new__(VzpCog)
    cog.last_report = None
    monkeypatch.setattr(vzp_module, "VZP_INGEST_CHANNEL_ID", 777)
    monkeypatch.setattr(vzp_module, "already_posted", AsyncMock(return_value=False))

    message = SimpleNamespace(
        id=2,
        channel=SimpleNamespace(id=999),
        content=json.dumps({"wars": [_war()]}),
        attachments=[],
        add_reaction=AsyncMock(),
    )
    await cog.on_message(message)
    # канал не тот — обработка не начиналась
    assert cog.last_report is None
