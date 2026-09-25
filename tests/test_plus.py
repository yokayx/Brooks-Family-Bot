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
