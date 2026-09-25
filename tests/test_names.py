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


def test_no_brackets_with_pipe() -> None:
    assert extract_name("Klyde | Илья") == "Klyde"
    assert extract_name("Klyde|Илья") == "Klyde"
    assert extract_name("Klyde Brooks | Илья") == "Klyde Brooks"


def test_no_brackets_no_pipe() -> None:
    assert extract_name("Klyde") == FALLBACK_NICK


def test_brackets_with_spaces_and_punctuation() -> None:
    assert extract_name("[ Klyde ] | Илья") == "Klyde"
    assert extract_name("[Klyde.] | Илья") == "Klyde"
    assert extract_name("[Klyde-1] | Илья") == "Klyde-1"
    assert extract_name("[Klyde'x] | Илья") == "Klyde'x"


def test_digit_first_is_not_a_tag() -> None:
    assert extract_name("[2pac] | Илья") == FALLBACK_NICK
    assert extract_name("2pac | Илья") == FALLBACK_NICK


def test_skip_non_latin_and_family_brackets() -> None:
    assert extract_name("[БС][Klyde] | Илья") == "Klyde"
    assert extract_name("[Brooks] Klyde | Илья") == "Klyde"
    assert extract_name("[Brooks][Klyde] | Илья") == "Klyde"


def test_cyrillic_before_pipe_is_not_a_tag() -> None:
    assert extract_name("Илья | Klyde") == FALLBACK_NICK


def test_empty() -> None:
    assert extract_name(None) == FALLBACK_NICK
    assert extract_name("") == FALLBACK_NICK
