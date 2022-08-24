from __future__ import annotations

import asyncio
import logging
import random
import re
import traceback
from enum import Enum
from typing import Any, Callable, Coroutine, Pattern

import discord
from discord import Member, Message, PartialEmoji, RawReactionActionEvent, User

from moobot.db.models import MoobloomEvent
from moobot.db.session import Session
from moobot.events import initialize_events
from moobot.settings import get_settings

settings = get_settings()
_logger = logging.getLogger(__name__)

_discord_bot_commands: dict[Pattern, Callable] = {}

AFFIRMATIONS = ["Okay", "Sure", "Sounds good", "No problem", "Roger that", "Got it"]
THANKS = [*AFFIRMATIONS, "Thanks", "Thank you"]
DEBUG_COMMAND_PREFIX = r"(d|debug) "


class ReactionAction(str, Enum):
    ADDED = "added"
    REMOVED = "removed"


ReactionHandler = Callable[[ReactionAction, PartialEmoji, User | Member], Coroutine[None, Any, Any]]


class DiscordBot:
    def __init__(
        self,
        client: discord.Client,
        command_prefix: str | None = "$",
    ) -> None:

        self.client = client
        self.command_prefix = command_prefix

        self.reaction_handlers: dict[int, ReactionHandler] = {}  # message ID -> reaction handler

    def get_command_from_message(self, message: Message) -> str | None:
        """
        Get the bot command string from a raw Discord message.

        If the message is not a bot command, return None.
        """
        # all mentions are automatically interpreted as commands
        if self.client.user is not None and self.client.user.mentioned_in(message):
            mention_regex = rf"<@!?{self.client.user.id}>"
            command = re.sub(mention_regex, "", message.content, 1).strip()
            return command

        # alternatively, commands can be prefixed with a string to indicate they are for the bot
        elif self.command_prefix is not None and message.content.startswith(self.command_prefix):
            command = message.content[len(self.command_prefix) :].strip()
            return command

        return None

    async def on_message(self, message: Message) -> None:
        # if this bot sent the message, never do anything
        if message.author == self.client.user:
            return

        # check if the message is a command and pass it to the appropriate command handler
        command = self.get_command_from_message(message)
        if command is None:
            return

        _logger.info(f"Received command: {command}")
        for pattern in _discord_bot_commands:
            match = pattern.match(command)
            if match:
                try:
                    await _discord_bot_commands[pattern](self, message, match)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    await message.channel.send(
                        f"Sorry {message.author.mention}! Something went wrong while running your"
                        f" command.```{traceback.format_exc()[-1900:]}```"
                    )
                    raise
                break

    async def on_reaction_change(
        self, action: ReactionAction, payload: RawReactionActionEvent
    ) -> None:
        # check if there are any registered handlers for reactions on this message
        if payload.message_id in self.reaction_handlers:
            user: User | Member | None
            if payload.guild_id is not None:
                guild = self.client.get_guild(payload.guild_id)
                if guild is None:
                    raise ValueError(f"guild {payload.guild_id} not found")
                user = (await guild.query_members(user_ids=[payload.user_id]))[0]
            else:
                user = self.client.get_user(payload.user_id)
            if user is None:
                raise ValueError(f"user {payload.user_id} not found")
            await self.reaction_handlers[payload.message_id](action, payload.emoji, user)

    @staticmethod
    def command(r: str) -> Callable[..., Any]:
        """
        Decorator for defining bot commands matching a given regex.

        After receiving a command, the bot will call the first @command function whose regex
        matches the given command.
        """

        def deco(f: Callable[..., Any]) -> Callable[..., Any]:
            _discord_bot_commands[re.compile(f"^{r}$", re.IGNORECASE)] = f
            return f

        return deco

    def affirm(self) -> str:
        return random.choice(AFFIRMATIONS)

    def thank(self) -> str:
        return random.choice(THANKS)

    @command(r"e refresh")
    async def refresh_events(self, message: Message, _command: re.Match) -> None:
        await initialize_events(self)
        await message.channel.send(f"{self.affirm()} {message.author.mention}")

    @command(r"e add (.+)")
    async def add_event(self, message: Message, command: re.Match) -> None:
        raw_event = command.group(1)
        parsed_event = MoobloomEvent.parse_raw(raw_event)
        with Session(expire_on_commit=False) as session:
            session.add(parsed_event)
            session.commit()
        await message.channel.send(
            f"{self.affirm()} {message.author.mention}, created event {parsed_event.name}"
        )
        await initialize_events(self)


async def start() -> None:
    loop = asyncio.get_running_loop()

    intents = discord.Intents(
        messages=True, guild_messages=True, message_content=True, guilds=True, reactions=True
    )
    client = discord.Client(intents=intents, loop=loop)
    discord_bot: DiscordBot = DiscordBot(client)

    @client.event
    async def on_ready() -> None:
        _logger.info(f"We have logged in as {client.user}")
        await initialize_events(discord_bot)

    @client.event
    async def on_message(message: Message) -> None:
        await discord_bot.on_message(message)

    @client.event
    async def on_raw_reaction_add(payload: RawReactionActionEvent) -> None:
        await discord_bot.on_reaction_change(ReactionAction.ADDED, payload)

    @client.event
    async def on_raw_reaction_remove(payload: RawReactionActionEvent) -> None:
        await discord_bot.on_reaction_change(ReactionAction.REMOVED, payload)

    await client.start(settings.discord_token)
