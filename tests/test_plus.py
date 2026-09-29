from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from bot.config import (
    FALLBACK_NICK,
    PLUS_KIND_GENERAL,
    PLUS_KIND_PINGS,
    PLUS_KIND_VZP,
    PLUS_PING_GENERAL_ROLE_ID,
    PLUS_PING_VZP_ROLE_ID,
)
from bot.plus.timeparse import parse_event_time

MSK = ZoneInfo("Europe/Moscow")


def test_parse_today_if_future() -> None:
    now = datetime(2026, 9, 23, 18, 0, tzinfo=MSK)
    stamp = parse_event_time("20:00", now=now)
    assert stamp.hour == 20
    assert stamp.day == 23


def test_parse_tomorrow_if_past() -> None:
    now = datetime(2026, 9, 23, 21, 0, tzinfo=MSK)
    stamp = parse_event_time("20.00", now=now)
    assert stamp.day == 24
    assert stamp.hour == 20


def test_kind_pings() -> None:
    assert PLUS_KIND_PINGS[PLUS_KIND_GENERAL] == PLUS_PING_GENERAL_ROLE_ID
    assert PLUS_KIND_PINGS[PLUS_KIND_VZP] == PLUS_PING_VZP_ROLE_ID
    assert PLUS_PING_GENERAL_ROLE_ID == 1552378409211142174
    assert PLUS_PING_VZP_ROLE_ID == 1551727236812640359


def test_parse_bad() -> None:
    with pytest.raises(ValueError):
        parse_event_time("вечер")
    with pytest.raises(ValueError):
        parse_event_time("25:00")


def _member(nick: str | None, user_id: int = 1):
    from types import SimpleNamespace

    return SimpleNamespace(id=user_id, nick=nick, display_name=nick or "User")


def test_game_name_from_brackets_and_pipe() -> None:
    from bot.plus.names import member_game_name

    assert member_game_name(_member("[Klyde] | Илья")) == "Klyde Brooks"
    assert member_game_name(_member("Klyde | Илья")) == "Klyde Brooks"


def test_game_name_no_double_family() -> None:
    from bot.plus.names import member_game_name

    assert member_game_name(_member("Klyde Brooks | Илья")) == "Klyde Brooks"
    assert member_game_name(_member("[Klyde_Brooks] | Илья")) == "Klyde_Brooks"


def test_game_name_fallback_shames_nick() -> None:
    from bot.plus.names import member_game_name

    assert member_game_name(_member("Илья | Клайд")) == FALLBACK_NICK


def test_participant_line_numbering() -> None:
    from bot.plus.names import participant_line

    member = _member("[Klyde] | Илья", user_id=42)
    assert participant_line(1, member, "M4") == "1. Klyde Brooks | M4"
    assert participant_line(2, member, "") == "2. Klyde Brooks"
    assert participant_line(3, member) == "3. Klyde Brooks"


def test_embed_lines_numbered() -> None:
    import json
    from datetime import datetime
    from types import SimpleNamespace

    from bot.cogs.plus import PlusCog

    def _guild() -> SimpleNamespace:
        members = {7: _member("[Klyde] | Илья", user_id=7)}
        return SimpleNamespace(get_member=lambda uid: members.get(uid))

    event = SimpleNamespace(
        event_time=datetime(2026, 9, 25, 20, 0, tzinfo=MSK),
        event_kind=PLUS_KIND_GENERAL,
        reason="капт",
        need_static=True,
        participants_json=json.dumps(
            {"7": {"user_id": 7, "static": "M4"}, "8": {"user_id": 8, "static": ""}},
            ensure_ascii=False,
        ),
    )
    embed = PlusCog.__new__(PlusCog).build_embed(_guild(), event)
    # участник 8 ушёл с сервера — в список не попадает
    assert embed.fields[0].value.splitlines() == ["1. Klyde Brooks | M4"]

    # сбор без статика — только номер и тег участника
    event.need_static = False
    embed = PlusCog.__new__(PlusCog).build_embed(_guild(), event)
    assert embed.fields[0].value.splitlines() == ["1. <@7>"]

    event.participants_json = "{}"
    embed = PlusCog.__new__(PlusCog).build_embed(_guild(), event)
    assert embed.fields[0].value == "Пока никто не записался."


def test_chunk_lines_keep_field_limit() -> None:
    from bot.cogs.plus import FIELD_LIMIT, _chunk_lines

    lines = [f"{i}. Name{i} Brooks | —" for i in range(100)]
    chunks = _chunk_lines(lines)
    assert len(chunks) > 1
    assert sum(len(chunk) for chunk in chunks) == len(lines)
    assert all(len("\n".join(chunk)) <= FIELD_LIMIT for chunk in chunks)


def test_static_must_be_digits() -> None:
    import asyncio
    from types import SimpleNamespace

    from bot.cogs.plus import StaticModal

    sent: list[dict] = []
    added: list[str | None] = []

    class _Cog:
        async def add_participant(self, interaction, event_id: int, static):
            added.append(static)

    class _Response:
        def is_done(self) -> bool:
            return False

        async def send_message(self, text: str, ephemeral: bool = False) -> None:
            sent.append({"text": text, "ephemeral": ephemeral})

    def _make(value: str) -> StaticModal:
        modal = StaticModal(_Cog(), 1)  # type: ignore[arg-type]
        modal.static._value = value
        return modal

    async def run() -> None:
        interaction = SimpleNamespace(response=_Response())
        await _make(" 12345 ").on_submit(interaction)
        assert added == ["12345"] and not sent

        await _make("m4a1").on_submit(interaction)
        assert len(sent) == 1 and len(added) == 1
        assert "только цифры" in sent[0]["text"] and sent[0]["ephemeral"]

        await _make("12 34").on_submit(interaction)
        assert len(added) == 1

    asyncio.run(run())


def test_event_time_is_shown_as_typed_msk() -> None:
    from bot.cogs.plus import _format_event_time

    # 17:00 UTC == 20:00 МСК
    stamp = datetime(2026, 9, 26, 17, 0, tzinfo=UTC)
    text = _format_event_time(stamp)
    assert text.startswith("20:00 МСК")
    assert "<t:" in text  # относительное «через N» оставляем
    assert _format_event_time(None) == "-"


def _member_with_roles(role_ids: list[int]):
    from types import SimpleNamespace

    return SimpleNamespace(
        id=1,
        nick="Klyde | Илья",
        roles=[SimpleNamespace(id=role_id) for role_id in role_ids],
    )


def test_vzp_roles_can_join_vzp_only() -> None:
    """Роли VZP ставят плюсы на VZP-сборы, но не на общие."""
    from bot.cogs.plus import join_denial
    from bot.config import (
        PLUS_KIND_GENERAL,
        PLUS_KIND_VZP,
        PLUS_VZP_ROLE_IDS,
        RANK_ROLE_IDS,
    )

    for role_id in PLUS_VZP_ROLE_IDS:
        assert join_denial(_member_with_roles([role_id]), PLUS_KIND_VZP) is None

    # Head VZP — ещё и ранг состава, общие сборы ему доступны и так.
    non_rank = [role_id for role_id in PLUS_VZP_ROLE_IDS if role_id not in RANK_ROLE_IDS]
    assert non_rank
    for role_id in non_rank:
        assert join_denial(_member_with_roles([role_id]), PLUS_KIND_GENERAL) is not None


def test_family_joins_any_kind() -> None:
    from bot.cogs.plus import join_denial
    from bot.config import PLUS_KIND_GENERAL, PLUS_KIND_VZP, RANK_ROLE_IDS

    rank = sorted(RANK_ROLE_IDS)[0]
    assert join_denial(_member_with_roles([rank]), PLUS_KIND_VZP) is None
    assert join_denial(_member_with_roles([rank]), PLUS_KIND_GENERAL) is None


def test_outsider_gets_kind_specific_denial() -> None:
    from bot.cogs.plus import FAMILY_JOIN_DENY, VZP_JOIN_DENY, join_denial
    from bot.config import PLUS_KIND_GENERAL, PLUS_KIND_VZP

    member = _member_with_roles([999])
    assert join_denial(member, PLUS_KIND_GENERAL) == FAMILY_JOIN_DENY
    assert join_denial(member, PLUS_KIND_VZP) == VZP_JOIN_DENY


def test_requested_vzp_role_ids() -> None:
    from bot.config import PLUS_VZP_ROLE_IDS

    assert PLUS_VZP_ROLE_IDS == (
        1551727304382611476,
        1551727236812640359,
        1553233826451431494,
        1551727082541813891,
    )


async def test_plus_button_denies_before_static_modal() -> None:
    """Кому нельзя — тот не дойдёт даже до модалки статик."""
    from unittest.mock import AsyncMock, MagicMock

    import discord

    from bot.cogs.plus import PlusEventView
    from bot.config import PLUS_KIND_VZP

    event = MagicMock()
    event.is_active = True
    event.need_static = True
    event.event_kind = PLUS_KIND_VZP
    cog = MagicMock()
    cog.get_event_from_message = AsyncMock(return_value=event)
    cog.add_participant = AsyncMock()

    view = PlusEventView(cog)
    member = MagicMock(spec=discord.Member)
    member.roles = []
    interaction = MagicMock()
    interaction.response = AsyncMock()
    interaction.user = member
    interaction.message = MagicMock(id=7)

    await view.plus_button.callback(interaction)

    interaction.response.send_modal.assert_not_called()
    cog.add_participant.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once()
    assert "VZP" in interaction.response.send_message.await_args.args[0]
