from __future__ import annotations

import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bot.cogs.roster import RosterCog
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
    def __init__(self, token: str, database_url: str) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        super().__init__(command_prefix="!", intents=intents)
        self._token = token
        self._database_url = database_url

    async def setup_hook(self) -> None:
        await init_db(self._database_url)
        await self.add_cog(RosterCog(self))

    def start_bot(self) -> None:
        self.run(self._token)


def main() -> None:
    load_dotenv()
    setup_logging()
    settings = load_settings()
    bot = BrooksBot(settings.discord_token, settings.database_url)
    bot.start_bot()


if __name__ == "__main__":
    main()
