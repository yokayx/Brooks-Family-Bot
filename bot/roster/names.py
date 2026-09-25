from __future__ import annotations

import re

from bot.config import FALLBACK_NICK, FAMILY_NAME

# Содержимое скобок: [Klyde] | Илья, [Klyde.] | Илья, [БС][Klyde] | Илья
_BRACKETS_RE = re.compile(r"\[([^\[\]]*)\]")

# Одна или несколько групп скобок в начале ника: [Brooks] Klyde | Илья
_LEADING_BRACKETS_RE = re.compile(r"^\s*(?:\[[^\[\]]*\]\s*)+")

# Игровой тег: латиница с первой буквы, дальше буквы/цифры/_/./-/пробел/апостроф
_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.'\- ]*")

# Чем обрезаем края найденного имени
_TRIM = " \t\r\n|·,–—-."

MAX_NAME_LEN = 32


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(_TRIM)).strip()


def _is_game_name(value: str) -> bool:
    if not value or len(value) > MAX_NAME_LEN:
        return False
    return _NAME_RE.fullmatch(value) is not None


def _is_family_tag(value: str) -> bool:
    return value.casefold() == FAMILY_NAME.casefold()


def _first_word(value: str) -> str:
    parts = value.split(" ")
    return parts[0] if parts else ""


def extract_name(profile: str | None) -> str:
    """Игровой тег из ника семьи.

    Понимает оба вида формы:

    - `[Klyde] | Илья` — тег в первых скобках с латиницей;
    - `Klyde | Илья` — скобок нет, тег — всё до первой `|`.

    Скобки без латиницы (`[БС][Klyde]`) и семейный тег (`[Brooks] Klyde`)
    пропускаются. Не начинается с буквы (цифра в начале) — не тег.
    """
    if not profile:
        return FALLBACK_NICK
    text = profile.strip()

    # 1. Первые скобки с латиницей.
    for content in _BRACKETS_RE.findall(text):
        candidate = _clean(content)
        if _is_game_name(candidate) and not _is_family_tag(candidate):
            return candidate

    # 2. Скобок нет или в них не тег — часть до первой `|`.
    if "|" in text:
        head = _LEADING_BRACKETS_RE.sub("", text.split("|", 1)[0])
        candidate = _clean(head)
        if not _is_game_name(candidate):
            candidate = _clean(_first_word(candidate))
        if _is_game_name(candidate) and not _is_family_tag(candidate):
            return candidate

    return FALLBACK_NICK
