import discord

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
    assert TICKETS_CATEGORY_ID == 1552394606975516804
    assert CLOSED_TICKETS_CATEGORY_ID == 1552394634616111178
    assert RECRUITER_ROLE_ID == 1453123003645952254
    assert TEST_ROLE_ID == 1550827936641454141
    assert APPLICATION_MEMBER_ROLE_ID == PLUS_PING_GENERAL_ROLE_ID
    assert APPLICATION_ACCEPT_ROLE_IDS == (TEST_ROLE_ID, APPLICATION_MEMBER_ROLE_ID)


def test_applications_menu_text() -> None:
    from bot.applications.forms import build_applications_text
    from bot.config import APPLICATION_KIND_ROLE_IDS, APPLICATION_KIND_VZP, TEST_ROLE_ID

    vzp_role = APPLICATION_KIND_ROLE_IDS[APPLICATION_KIND_VZP]
    text = build_applications_text(main_open=True, vzp_open=False)
    assert text.startswith("# Оформление заявки в семью")
    assert f"<@&{TEST_ROLE_ID}>: Нужны откаты с Арены." in text
    assert f"<@&{vzp_role}>: Нужны откаты с VZP и Арены." in text
    # статусы: у Main открыт, у VZP закрыт
    assert "> **Статус набора:** :on:" in text
    assert "> **Статус набора:** :off:" in text
    assert "Возраст от 15 лет" in text

    closed = build_applications_text(main_open=False, vzp_open=False)
    assert ":on:" not in closed


def test_application_select_menu() -> None:
    from bot.cogs.applications import ApplicationsCog, ApplicationSelectView
    from bot.config import APPLICATION_KIND_MAIN, APPLICATION_KIND_VZP

    view = ApplicationSelectView(ApplicationsCog.__new__(ApplicationsCog))
    select = next(child for child in view.children if isinstance(child, discord.ui.Select))
    assert select.custom_id == "applications:kind"
    options = {option.value: option for option in select.options}
    assert set(options) == {APPLICATION_KIND_MAIN, APPLICATION_KIND_VZP}
    assert options[APPLICATION_KIND_MAIN].label == "Заявка на Young"
    assert options[APPLICATION_KIND_MAIN].description == "Заполнить заявку в семью."
    assert options[APPLICATION_KIND_VZP].label == "Заявка на Test"
    assert options[APPLICATION_KIND_VZP].description == "Заполнить заявку в семью на VZP."


def test_control_panel_buttons() -> None:
    from bot.cogs.applications import ApplicationsCog, ControlPanelView

    view = ControlPanelView(ApplicationsCog.__new__(ApplicationsCog))
    ids = {child.custom_id for child in view.children if isinstance(child, discord.ui.Button)}
    assert ids == {
        "control:main:open",
        "control:main:close",
        "control:vzp:open",
        "control:vzp:close",
        "control:main:form",
        "control:vzp:form",
    }
    assert view.timeout is None  # панель переживает рестарт
