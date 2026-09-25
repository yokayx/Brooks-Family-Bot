from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bot.config import MOSCOW_TZ

_MSK = ZoneInfo(MOSCOW_TZ)
_TIME_RE = re.compile(r"^(\d{1,2})[:.\-\s](\d{2})$")


def parse_event_time(raw: str, *, now: datetime | None = None) -> datetime:
    """HH:MM по Москве. Если время уже прошло сегодня — завтра."""
    text = (raw or "").strip()
    match = _TIME_RE.match(text)
    if match is None:
        raise ValueError("Время в формате ЧЧ:ММ, например 20:00")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("Некорректное время")
    current = now or datetime.now(_MSK)
    if current.tzinfo is None:
        current = current.replace(tzinfo=_MSK)
    else:
        current = current.astimezone(_MSK)
    stamp = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if stamp <= current:
        stamp += timedelta(days=1)
    return stamp
