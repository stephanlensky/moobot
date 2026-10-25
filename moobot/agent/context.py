from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord import Message

    from moobot.discord.discord_bot import DiscordBot
    from moobot.discord.views.agent_action import AgentActionView


@dataclass
class AgentContext:
    bot: DiscordBot
    channel_id: int
    author_id: int
    author_name: str
    message: Message
    views: list[AgentActionView] = field(default_factory=list)
