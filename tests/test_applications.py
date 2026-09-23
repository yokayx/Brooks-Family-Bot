from bot.applications.dates import parse_date
from bot.config import (
    APPLICATION_ACCEPT_ROLE_IDS,
    APPLICATION_MEMBER_ROLE_ID,
    APPLICATIONS_CHANNEL_ID,
    CLOSED_TICKETS_CATEGORY_ID,
    PLUS_PING_GENERAL_ROLE_ID,
    RECRUITER_ROLE_ID,
    TEST_ROLE_ID,
    TICKETS_CATEGORY_ID,
)


def test_parse_numeric() -> None:
    assert parse_date("17.05") == (17, 5)
    assert parse_date("17/05") == (17, 5)
    assert parse_date("7-1") == (7, 1)


def test_parse_words() -> None:
    assert parse_date("17 мая") == (17, 5)
    assert parse_date("may 17") == (17, 5)
    assert parse_date("17 May") == (17, 5)


def test_parse_bad() -> None:
    assert parse_date("") is None
    assert parse_date("вечер") is None
    assert parse_date("32.05") is None
    assert parse_date("17.13") is None


def test_application_ids() -> None:
    assert APPLICATIONS_CHANNEL_ID == 1453123004308390116
    assert TICKETS_CATEGORY_ID == 1552383563150921870
    assert CLOSED_TICKETS_CATEGORY_ID == 1552383583669330010
    assert RECRUITER_ROLE_ID == 1453123003645952254
    assert TEST_ROLE_ID == 1550827936641454141
    assert APPLICATION_MEMBER_ROLE_ID == PLUS_PING_GENERAL_ROLE_ID
    assert APPLICATION_ACCEPT_ROLE_IDS == (TEST_ROLE_ID, APPLICATION_MEMBER_ROLE_ID)
