import re

from bot.config import FALLBACK_NICK

# Первые [] с латинским именем: [Klyde] | Илья → Klyde
_NAME_RE = re.compile(r"\[([A-Za-z][A-Za-z0-9_]*)\]")


def extract_name(profile: str | None) -> str:
    if not profile:
        return FALLBACK_NICK
    match = _NAME_RE.search(profile)
    if match:
        return match.group(1)
    return FALLBACK_NICK
