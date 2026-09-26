from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from bot.cogs.logs import LogsCog, format_time_ago, format_years_ago


def test_format_ago() -> None:
    now = datetime.now(UTC)
    assert format_years_ago(now - timedelta(days=400)) == "1 г."
    assert format_years_ago(now - timedelta(days=70)) == "2 мес."
    assert format_years_ago(now - timedelta(days=5)) == "5 д."
    assert format_time_ago(None) == "неизвестно"


async def test_send_skips_unconfigured_channel() -> None:
    cog = LogsCog.__new__(LogsCog)
    # 0 = канал логов не задан в config -> молчим, без обращений к API.
    await cog._send(0, "что-то случилось")


async def test_deleted_message_is_logged(monkeypatch) -> None:
    cog = LogsCog.__new__(LogsCog)
    cog.bot = SimpleNamespace(get_channel=lambda channel_id: None)
    cog.message_cache = OrderedDict()

    sent: list[tuple[int, str]] = []

    async def fake_send(_self: LogsCog, channel_id: int, text: str) -> None:
        sent.append((channel_id, text))

    monkeypatch.setattr(LogsCog, "_send", fake_send)

    message = SimpleNamespace(
        id=11,
        guild=SimpleNamespace(id=1),
        channel=SimpleNamespace(id=500),
        author=SimpleNamespace(id=7, bot=False, mention="<@7>"),
        content="привет",
        attachments=[],
    )

    await cog.on_message(message)
    await cog.on_message_delete(message)

    assert sent, "лог удаления не отправлен"
    assert sent[0][1].startswith("**Удалено сообщение**")
    assert "привет" in sent[0][1]
    assert "<@7>" in sent[0][1]
    assert "<#500>" in sent[0][1]


async def test_edited_message_is_logged(monkeypatch) -> None:
    cog = LogsCog.__new__(LogsCog)
    cog.bot = SimpleNamespace(get_channel=lambda channel_id: None)
    cog.message_cache = OrderedDict()

    sent: list[tuple[int, str]] = []

    async def fake_send(_self: LogsCog, channel_id: int, text: str) -> None:
        sent.append((channel_id, text))

    monkeypatch.setattr(LogsCog, "_send", fake_send)

    base = dict(
        id=12,
        guild=SimpleNamespace(id=1),
        channel=SimpleNamespace(id=500),
        author=SimpleNamespace(id=7, bot=False, mention="<@7>"),
        attachments=[],
    )
    before = SimpleNamespace(content="старый", **base)
    after = SimpleNamespace(content="новый", **base)

    await cog.on_message_edit(before, after)
    assert "старый" in sent[0][1] and "новый" in sent[0][1]
