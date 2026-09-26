from types import SimpleNamespace

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
    from bot.config import (
        APPLICATION_CLOSED_EMOJI,
        APPLICATION_KIND_ROLE_IDS,
        APPLICATION_KIND_VZP,
        APPLICATION_OPEN_EMOJI,
        TEST_ROLE_ID,
    )

    vzp_role = APPLICATION_KIND_ROLE_IDS[APPLICATION_KIND_VZP]
    text = build_applications_text(main_open=True, vzp_open=False)
    assert text.startswith("# Оформление заявки в семью")
    assert f"<@&{TEST_ROLE_ID}>: Нужны откаты с Арены." in text
    assert f"<@&{vzp_role}>: Нужны откаты с VZP и Арены." in text
    # статусы: у Main открыт, у VZP закрыт — кастомными эмодзи
    assert f"> **Статус набора:** {APPLICATION_OPEN_EMOJI}" in text
    assert f"> **Статус набора:** {APPLICATION_CLOSED_EMOJI}" in text
    assert "Возраст от 15 лет" in text

    closed = build_applications_text(main_open=False, vzp_open=False)
    assert APPLICATION_OPEN_EMOJI not in closed


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
    """Одна кнопка на функцию: нажал — включил, нажал ещё раз — выключил."""
    from bot.cogs.applications import ApplicationsCog, ControlPanelView

    view = ControlPanelView(ApplicationsCog.__new__(ApplicationsCog))
    buttons = [child for child in view.children if isinstance(child, discord.ui.Button)]
    assert {button.custom_id for button in buttons} == {
        "control:main:toggle",
        "control:vzp:toggle",
        "control:main:form",
        "control:vzp:form",
    }
    labels = [button.label for button in buttons]
    assert "Набор Young" in labels and "Набор Test" in labels
    assert view.timeout is None  # панель переживает рестарт


def test_control_panel_status_lines() -> None:
    from bot.applications.forms import build_control_panel_description
    from bot.config import APPLICATION_CLOSED_EMOJI, APPLICATION_OPEN_EMOJI

    text = build_control_panel_description(main_open=True, vzp_open=False)
    assert text == f"{APPLICATION_OPEN_EMOJI} Набор Young\n{APPLICATION_CLOSED_EMOJI} Набор Test"


async def test_resolve_text_channel_falls_back_to_fetch() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from bot.cogs.applications import ApplicationsCog

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 1553239900176908289
    bot = MagicMock()
    bot.get_channel.return_value = None
    bot.fetch_channel = AsyncMock(return_value=channel)

    cog = ApplicationsCog.__new__(ApplicationsCog)
    cog.bot = bot
    resolved = await cog._resolve_text_channel(channel.id)

    assert resolved is channel
    bot.fetch_channel.assert_awaited_once_with(channel.id)


def test_send_commands_removed() -> None:
    """Меню заявок и панель публикуются сами — команд отправки быть не должно."""
    from bot.cogs.applications import ApplicationsCog
    from bot.cogs.core import CoreCog

    applications = {command.name for command in ApplicationsCog.__cog_app_commands__}
    assert applications == {"настроить-форму"}
    assert "синк" in {command.name for command in CoreCog.__cog_app_commands__}


def test_applications_menu_embed() -> None:
    from bot.applications.forms import build_applications_embed
    from bot.config import APPLICATION_KIND_ROLE_IDS, APPLICATION_KIND_VZP, TEST_ROLE_ID

    vzp_role = APPLICATION_KIND_ROLE_IDS[APPLICATION_KIND_VZP]
    embed = build_applications_embed(main_open=True, vzp_open=False)
    assert embed.title == "Оформление заявки в семью"
    assert f"<@&{TEST_ROLE_ID}>" in embed.description
    assert f"<@&{vzp_role}>" in embed.description
    assert ":on:" in embed.description and ":off:" in embed.description


def test_answers_embed_fields() -> None:
    from bot.cogs.applications import _answers_embed

    embed = _answers_embed(
        "Анкета заполнена",
        [{"question": "Ник", "answer": "Klyde"}, {"question": "Возраст", "answer": "  "}],
    )
    assert embed.title == "Анкета заполнена"
    assert [field.name for field in embed.fields] == ["Ник", "Возраст"]
    assert embed.fields[0].value == "Klyde"
    assert embed.fields[1].value == "—"


async def test_ticket_message_pings_recruiters(monkeypatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from bot.cogs.applications import ApplicationsCog
    from bot.config import APPLICATION_PING_ROLE_IDS

    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 900
    channel.send = AsyncMock()
    author = MagicMock(spec=discord.Member)
    author.id = 42
    author.bot = False
    author.mention = "<@42>"
    message = SimpleNamespace(
        guild=MagicMock(spec=discord.Guild),
        author=author,
        channel=channel,
        content="Мой ответ",
    )

    ticket = SimpleNamespace(
        id=7, channel_id=900, applicant_id=42, status="open", applicant_replied=False
    )

    cog = ApplicationsCog.__new__(ApplicationsCog)

    async def fake_get_ticket(_self: ApplicationsCog, channel_id: int):
        return ticket if channel_id == 900 else None

    async def fake_mark(_self: ApplicationsCog, ticket_id: int) -> None:
        ticket.applicant_replied = True

    monkeypatch.setattr(ApplicationsCog, "get_ticket_for_channel", fake_get_ticket)
    monkeypatch.setattr(ApplicationsCog, "_mark_replied", fake_mark)

    await cog.on_message(message)

    sent = channel.send.await_args.args[0]
    for role_id in APPLICATION_PING_ROLE_IDS:
        assert f"<@&{role_id}>" in sent

    # второй раз не тегаем
    channel.send.reset_mock()
    await cog.on_message(message)
    channel.send.assert_not_awaited()
