from bot.config import FALLBACK_NICK
from bot.roster.names import extract_name


def test_brackets_gta_nick() -> None:
    assert extract_name("[Klyde] | Илья") == "Klyde"


def test_underscore_name() -> None:
    assert extract_name("fam [John_Doe] 10") == "John_Doe"


def test_first_brackets_win() -> None:
    assert extract_name("[Klyde] [Other]") == "Klyde"


def test_cyrillic_brackets_fallback() -> None:
    assert extract_name("[Илья] | test") == FALLBACK_NICK


def test_no_brackets() -> None:
    assert extract_name("Klyde | Илья") == FALLBACK_NICK


def test_empty() -> None:
    assert extract_name(None) == FALLBACK_NICK
    assert extract_name("") == FALLBACK_NICK
