from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from bot.config import MOSCOW_TZ

_MSK = ZoneInfo(MOSCOW_TZ)


def parse_dt(value: object) -> datetime | None:
    """Время из API (`2026-09-25T19:33:59.000Z`) в МСК, None если не распарсилось."""
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(_MSK)


def fmt_dt(value: object) -> str:
    stamp = parse_dt(value)
    if stamp is None:
        return "—"
    return stamp.strftime("%d.%m %H:%M")
