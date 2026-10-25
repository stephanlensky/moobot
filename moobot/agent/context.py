from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot


@dataclass
class AgentContext:
    bot: DiscordBot
    channel_id: int
    author_id: int
    author_name: str
