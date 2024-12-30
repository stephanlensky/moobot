import discord
from discord import Emoji

_emojis: list[Emoji] = []


async def get_custom_emoji_by_name(client: discord.Client, emoji: str) -> Emoji:
    for guild in client.guilds:
        _emojis.extend(await guild.fetch_emojis())

    try:
        return next(e for e in _emojis if e.name == emoji)
    except StopIteration:
        raise ValueError(f"Custom emoji {emoji} not found")
