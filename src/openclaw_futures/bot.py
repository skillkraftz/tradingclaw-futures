"""Discord bot entry point."""
from __future__ import annotations

import os

import discord

from openclaw_futures.config import DATA_DIR
from openclaw_futures.discord.commands import register_commands
from openclaw_futures.providers.file_provider import FileMarketDataProvider
from openclaw_futures.services import OpenClawService


class OpenClawBot(discord.Client):
    def __init__(self, service: OpenClawService):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)
        self.service = service
        register_commands(self.tree, self.service)

    async def setup_hook(self) -> None:
        await self.tree.sync()


def main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required")
    provider = FileMarketDataProvider(DATA_DIR)
    service = OpenClawService(provider)
    bot = OpenClawBot(service)
    bot.run(token)


if __name__ == "__main__":
    main()
