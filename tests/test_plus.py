from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot.config import (
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


def test_game_name_empty_when_no_tag() -> None:
    from bot.plus.names import member_game_name

    assert member_game_name(_member("Илья | Клайд")) == ""


def test_participant_line_is_tag_first() -> None:
    from bot.plus.names import participant_line

    member = _member("[Klyde] | Илья", user_id=42)
    assert participant_line(42, member) == "<@42> | Klyde Brooks"
    assert participant_line(42, None) == "<@42>"
    assert participant_line(42, _member("Илья | Клайд", user_id=42)) == "<@42>"


def test_embed_lines_use_tag_not_number() -> None:
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
    assert embed.fields[0].value.splitlines() == ["<@7> | Klyde Brooks | M4", "<@8> | —"]

    event.need_static = False
    embed = PlusCog.__new__(PlusCog).build_embed(_guild(), event)
    assert embed.fields[0].value.splitlines() == ["<@7> | Klyde Brooks", "<@8>"]

    event.participants_json = "{}"
    embed = PlusCog.__new__(PlusCog).build_embed(_guild(), event)
    assert embed.fields[0].value == "Пока никто не записался."


def test_chunk_lines_keep_field_limit() -> None:
    from bot.cogs.plus import FIELD_LIMIT, _chunk_lines

    lines = [f"<@{i}> | Name{i} Brooks | —" for i in range(100)]
    chunks = _chunk_lines(lines)
    assert len(chunks) > 1
    assert sum(len(chunk) for chunk in chunks) == len(lines)
    assert all(len("\n".join(chunk)) <= FIELD_LIMIT for chunk in chunks)
