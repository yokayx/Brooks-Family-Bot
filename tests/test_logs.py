from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from bot.cogs.logs import (
    LogsCog,
    humanize_age,
    truncate,
    truncate_codeblock,
)


def test_helpers() -> None:
    assert truncate("короткий", 100) == "короткий"
    assert truncate("_" * 20, 10) == "_______..."
    assert truncate(None, 5) == ""
    assert truncate_codeblock("x" * 100, 30, lang="text").startswith("```text")
    assert humanize_age(None) == "неизвестно"


def test_categories_are_mapped() -> None:
    """Все категории из конфига обязаны быть в маппинге кога."""
    assert set(LogsCog.CATEGORY_CHANNELS) == {
        "moderation",
        "voice",
        "text",
        "member",
        "invite",
        "server",
        "audit",
        "bot-live",
    }


def test_log_channels_configured() -> None:
    """Все категории логов обязаны быть настроены (id != 0)."""
    empty = [name for name, channel_id in LogsCog.CATEGORY_CHANNELS.items() if not channel_id]
    assert not empty, f"каналы логов не настроены: {', '.join(empty)}"


async def test_unconfigured_category_is_skipped(monkeypatch) -> None:
    """id = 0 в конфиге — лог молча пропускается, без обращений к API."""
    cog = LogsCog.__new__(LogsCog)
    cog.bot = MagicMock()
    cog.bot.fetch_channel = AsyncMock()
    monkeypatch.setitem(LogsCog.CATEGORY_CHANNELS, "text", 0)
    assert await cog.get_log_channel("text") is None
    cog.bot.fetch_channel.assert_not_awaited()


async def test_deleted_message_is_logged(monkeypatch) -> None:
    cog = LogsCog.__new__(LogsCog)
    cog.bot = MagicMock()
    cog.bot.get_channel.return_value = None

    sent: list[tuple[str, discord.Embed]] = []

    async def fake_send(
        _self: LogsCog, category: str, embed: discord.Embed, files: list | None = None
    ) -> None:
        sent.append((category, embed))

    async def fake_audit(_self: LogsCog, guild, action, target_id: int) -> None:
        return None

    monkeypatch.setattr(LogsCog, "safe_send_log", fake_send)
    monkeypatch.setattr(LogsCog, "get_audit_executor", fake_audit)

    author = SimpleNamespace(
        id=7,
        bot=False,
        mention="<@7>",
        display_avatar=SimpleNamespace(url="https://cdn/avatar.png"),
    )
    message = SimpleNamespace(
        id=11,
        author=author,
        guild=SimpleNamespace(id=1),
        channel=SimpleNamespace(id=500, mention="<#500>"),
        content="привет",
        attachments=[],
    )

    await cog.on_message_delete(message)

    assert sent, "лог удаления не отправлен"
    category, embed = sent[0]
    assert category == "text"
    assert "удалено" in embed.title.lower()
    assert "привет" in embed.fields[2].value
    assert "<#500>" in embed.fields[0].value


async def test_edited_message_is_logged(monkeypatch) -> None:
    cog = LogsCog.__new__(LogsCog)
    cog.bot = MagicMock()

    sent: list[tuple[str, discord.Embed]] = []

    async def fake_send(
        _self: LogsCog, category: str, embed: discord.Embed, files: list | None = None
    ) -> None:
        sent.append((category, embed))

    monkeypatch.setattr(LogsCog, "safe_send_log", fake_send)

    base = dict(
        id=12,
        guild=SimpleNamespace(id=1),
        channel=SimpleNamespace(id=500, mention="<#500>"),
        author=SimpleNamespace(
            bot=False,
            mention="<@7>",
            display_avatar=SimpleNamespace(url="https://cdn/avatar.png"),
        ),
    )
    before = SimpleNamespace(content="старый текст", **base)
    after = SimpleNamespace(content="старый новый", **base)

    await cog.on_message_edit(before, after)

    category, embed = sent[0]
    assert category == "text"
    assert "старый" in embed.fields[1].value
    assert "**новый**" in embed.fields[1].value


async def test_voice_join_is_logged(monkeypatch) -> None:
    cog = LogsCog.__new__(LogsCog)
    cog.bot = MagicMock()
    cog.bot.get_channel.return_value = None

    sent: list[tuple[str, discord.Embed]] = []

    async def fake_send(
        _self: LogsCog, category: str, embed: discord.Embed, files: list | None = None
    ) -> None:
        sent.append((category, embed))

    monkeypatch.setattr(LogsCog, "safe_send_log", fake_send)

    channel = MagicMock(spec=discord.VoiceChannel)
    channel.mention = "<#900>"
    channel.type = discord.ChannelType.voice
    member = SimpleNamespace(
        id=7,
        mention="<@7>",
        guild=SimpleNamespace(id=1),
        display_avatar=SimpleNamespace(url="https://cdn/avatar.png"),
    )

    await cog.on_voice_state_update(
        member,
        SimpleNamespace(channel=None),
        SimpleNamespace(channel=channel),
    )

    category, embed = sent[0]
    assert category == "voice"
    assert "войс" in embed.title.lower()
    assert "<#900>" in embed.description
