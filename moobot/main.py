import asyncio

from moobot.discord import discord_bot


def main() -> None:
    asyncio.run(discord_bot.start())


if __name__ == "__main__":
    main()
