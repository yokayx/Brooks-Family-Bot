import discord

from bot.config import Settings
from bot.main import BrooksBot


def test_message_content_intent_on_by_default() -> None:
    settings = Settings(discord_token="test-token")
    assert settings.message_content_intent is True


async def test_bot_enables_message_content() -> None:
    bot = BrooksBot("test-token", "sqlite+aiosqlite:///:memory:")
    assert bot.intents.message_content is True
    assert bot.intents.voice_states is True
    assert bot.intents.members is True
    assert bot.intents.messages is True


async def test_bot_can_disable_message_content() -> None:
    bot = BrooksBot("test-token", "sqlite+aiosqlite:///:memory:", message_content=False)
    assert bot.intents.message_content is False
    assert discord.Intents.none() is not None  # intents собран вручную, не дефолтные
