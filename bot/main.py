from __future__ import annotations

import logging
import pkgutil

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bot import cogs as cogs_package
from bot.config import load_settings
from bot.db import init_db

log = logging.getLogger("brooks")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("discord").setLevel(logging.WARNING)


class BrooksBot(commands.Bot):
    def __init__(self, token: str, database_url: str, *, message_content: bool = False) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.voice_states = True
        intents.message_content = message_content
        super().__init__(command_prefix="!", intents=intents)
        self._token = token
        self._database_url = database_url

    async def setup_hook(self) -> None:
        await init_db(self._database_url)
        await self.load_cogs()

    async def load_cogs(self) -> None:
        loaded: list[str] = []
        for module in pkgutil.iter_modules(cogs_package.__path__):
            if module.name.startswith("_"):
                continue
            ext = f"{cogs_package.__name__}.{module.name}"
            await self.load_extension(ext)
            loaded.append(ext)
        log.info("cogs loaded: %s", ", ".join(loaded) or "(none)")

    def start_bot(self) -> None:
        self.run(self._token)


def main() -> None:
    load_dotenv()
    setup_logging()
    settings = load_settings()
    bot = BrooksBot(
        settings.discord_token,
        settings.database_url,
        message_content=settings.message_content_intent,
    )
    bot.start_bot()


if __name__ == "__main__":
    main()
