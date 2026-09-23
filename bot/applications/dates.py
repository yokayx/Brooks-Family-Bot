from __future__ import annotations

import re
from datetime import datetime

_MONTHS = {
    "января": 1,
    "январь": 1,
    "янв": 1,
    "january": 1,
    "jan": 1,
    "февраля": 2,
    "февраль": 2,
    "фев": 2,
    "february": 2,
    "feb": 2,
    "марта": 3,
    "март": 3,
    "мар": 3,
    "march": 3,
    "mar": 3,
    "апреля": 4,
    "апрель": 4,
    "апр": 4,
    "april": 4,
    "apr": 4,
    "мая": 5,
    "май": 5,
    "may": 5,
    "июня": 6,
    "июнь": 6,
    "июн": 6,
    "june": 6,
    "jun": 6,
    "июля": 7,
    "июль": 7,
    "июл": 7,
    "july": 7,
    "jul": 7,
    "августа": 8,
    "август": 8,
    "авг": 8,
    "august": 8,
    "aug": 8,
    "сентября": 9,
    "сентябрь": 9,
    "сен": 9,
    "сент": 9,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "октября": 10,
    "октябрь": 10,
    "окт": 10,
    "october": 10,
    "oct": 10,
    "ноября": 11,
    "ноябрь": 11,
    "ноя": 11,
    "november": 11,
    "nov": 11,
    "декабря": 12,
    "декабрь": 12,
    "дек": 12,
    "december": 12,
    "dec": 12,
}

_NUMERIC = re.compile(r"^(\d{1,2})[./-](\d{1,2})(?:[./-]\d{2,4})?$")
_DAY_MONTH = re.compile(r"^(\d{1,2})\s+([a-zа-яё]+)$")
_MONTH_DAY = re.compile(r"^([a-zа-яё]+)\s+(\d{1,2})$")


def _valid(day: int, month: int) -> tuple[int, int] | None:
    try:
        datetime(2000, month, day)
    except ValueError:
        return None
    return day, month


def parse_date(raw: str) -> tuple[int, int] | None:
    """День и месяц: 17.05, 17 мая, may 17. Год не нужен."""
    text = (raw or "").strip().lower()
    if not text:
        return None
    match = _NUMERIC.fullmatch(text)
    if match:
        return _valid(int(match.group(1)), int(match.group(2)))
    match = _DAY_MONTH.fullmatch(text)
    if match:
        month = _MONTHS.get(match.group(2))
        if month:
            return _valid(int(match.group(1)), month)
    match = _MONTH_DAY.fullmatch(text)
    if match:
        month = _MONTHS.get(match.group(1))
        if month:
            return _valid(int(match.group(2)), month)
    return None
