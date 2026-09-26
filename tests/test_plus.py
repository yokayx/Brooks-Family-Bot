from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot.config import (
    FALLBACK_NICK,
    PLUS_KIND_GENERAL,
    PLUS_KIND_PINGS,
    PLUS_KIND_VZP,
    PLUS_PING_GENERAL_ROLE_ID,
    PLUS_PING_VZP_ROLE_ID,
)
from bot.plus.timeparse import parse_event_time

MSK = ZoneInfo("Europe/Moscow")


def test_parse_today_if_future() -> None:
    now = datetime(2026, 9, 23, 18, 0, tzinfo=MSK)
    stamp = parse_event_time("20:00", now=now)
    assert stamp.hour == 20
    assert stamp.day == 23


def test_parse_tomorrow_if_past() -> None:
    now = datetime(2026, 9, 23, 21, 0, tzinfo=MSK)
    stamp = parse_event_time("20.00", now=now)
    assert stamp.day == 24
    assert stamp.hour == 20


def test_kind_pings() -> None:
    assert PLUS_KIND_PINGS[PLUS_KIND_GENERAL] == PLUS_PING_GENERAL_ROLE_ID
    assert PLUS_KIND_PINGS[PLUS_KIND_VZP] == PLUS_PING_VZP_ROLE_ID
    assert PLUS_PING_GENERAL_ROLE_ID == 1552378409211142174
    assert PLUS_PING_VZP_ROLE_ID == 1551727236812640359


def test_parse_bad() -> None:
    with pytest.raises(ValueError):
        parse_event_time("вечер")
    with pytest.raises(ValueError):
        parse_event_time("25:00")


def _member(nick: str | None, user_id: int = 1):
    from types import SimpleNamespace

    return SimpleNamespace(id=user_id, nick=nick, display_name=nick or "User")


def test_game_name_from_brackets_and_pipe() -> None:
    from bot.plus.names import member_game_name

    assert member_game_name(_member("[Klyde] | Илья")) == "Klyde Brooks"
    assert member_game_name(_member("Klyde | Илья")) == "Klyde Brooks"


def test_game_name_no_double_family() -> None:
    from bot.plus.names import member_game_name

    assert member_game_name(_member("Klyde Brooks | Илья")) == "Klyde Brooks"
    assert member_game_name(_member("[Klyde_Brooks] | Илья")) == "Klyde_Brooks"


def test_game_name_fallback_shames_nick() -> None:
    from bot.plus.names import member_game_name

    assert member_game_name(_member("Илья | Клайд")) == FALLBACK_NICK


def test_participant_line_numbering() -> None:
    from bot.plus.names import participant_line

    member = _member("[Klyde] | Илья", user_id=42)
    assert participant_line(1, member, "M4") == "1. Klyde Brooks | M4"
    assert participant_line(2, member, "") == "2. Klyde Brooks"
    assert participant_line(3, member) == "3. Klyde Brooks"


def test_embed_lines_numbered() -> None:
    import json
    from datetime import datetime
    from types import SimpleNamespace

    from bot.cogs.plus import PlusCog

    def _guild() -> SimpleNamespace:
        members = {7: _member("[Klyde] | Илья", user_id=7)}
        return SimpleNamespace(get_member=lambda uid: members.get(uid))

    event = SimpleNamespace(
        event_time=datetime(2026, 9, 25, 20, 0, tzinfo=MSK),
        event_kind=PLUS_KIND_GENERAL,
        reason="капт",
        need_static=True,
        participants_json=json.dumps(
            {"7": {"user_id": 7, "static": "M4"}, "8": {"user_id": 8, "static": ""}},
            ensure_ascii=False,
        ),
    )
    embed = PlusCog.__new__(PlusCog).build_embed(_guild(), event)
    # участник 8 ушёл с сервера — в список не попадает
    assert embed.fields[0].value.splitlines() == ["1. Klyde Brooks | M4"]

    # сбор без статика — только номер и тег участника
    event.need_static = False
    embed = PlusCog.__new__(PlusCog).build_embed(_guild(), event)
    assert embed.fields[0].value.splitlines() == ["1. <@7>"]

    event.participants_json = "{}"
    embed = PlusCog.__new__(PlusCog).build_embed(_guild(), event)
    assert embed.fields[0].value == "Пока никто не записался."


def test_chunk_lines_keep_field_limit() -> None:
    from bot.cogs.plus import FIELD_LIMIT, _chunk_lines

    lines = [f"{i}. Name{i} Brooks | —" for i in range(100)]
    chunks = _chunk_lines(lines)
    assert len(chunks) > 1
    assert sum(len(chunk) for chunk in chunks) == len(lines)
    assert all(len("\n".join(chunk)) <= FIELD_LIMIT for chunk in chunks)


def test_static_must_be_digits() -> None:
    import asyncio
    from types import SimpleNamespace

    from bot.cogs.plus import StaticModal

    sent: list[dict] = []
    added: list[str | None] = []

    class _Cog:
        async def add_participant(self, interaction, event_id: int, static):
            added.append(static)

    class _Response:
        def is_done(self) -> bool:
            return False

        async def send_message(self, text: str, ephemeral: bool = False) -> None:
            sent.append({"text": text, "ephemeral": ephemeral})

    def _make(value: str) -> StaticModal:
        modal = StaticModal(_Cog(), 1)  # type: ignore[arg-type]
        modal.static._value = value
        return modal

    async def run() -> None:
        interaction = SimpleNamespace(response=_Response())
        await _make(" 12345 ").on_submit(interaction)
        assert added == ["12345"] and not sent

        await _make("m4a1").on_submit(interaction)
        assert len(sent) == 1 and len(added) == 1
        assert "только цифры" in sent[0]["text"] and sent[0]["ephemeral"]

        await _make("12 34").on_submit(interaction)
        assert len(added) == 1

    asyncio.run(run())
