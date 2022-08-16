from __future__ import annotations

import asyncio
import logging
import random
import re
import traceback
from pathlib import Path
from typing import Any, Callable, Coroutine, Pattern

import discord
from discord import Member, Message, Reaction, Thread, User

from moobot.discord.thread_interaction import ThreadInteraction
from moobot.load_events import load_events_from_file
from moobot.settings import get_settings

settings = get_settings()
_logger = logging.getLogger(__name__)

_discord_bot_commands: dict[Pattern, Callable] = {}

AFFIRMATIONS = ["Okay", "Sure", "Sounds good", "No problem", "Roger that", "Got it"]
THANKS = [*AFFIRMATIONS, "Thanks", "Thank you"]
DEBUG_COMMAND_PREFIX = r"(d|debug) "

ReactionHandler = Callable[[Reaction, User | Member], Coroutine[None, Any, Any]]


class DiscordNotifierBot:
    def __init__(
        self,
        client: discord.Client,
        command_prefix: str | None = "$",
    ) -> None:

        self.client = client
        self.command_prefix = command_prefix

        self.active_threads: dict[int, ThreadInteraction] = {}  # thread ID -> setup handler
        self.reaction_handlers: dict[int, ReactionHandler] = {}  # message ID -> reaction handler

        # moobloom stuff
        load_events_from_file(Path("moobloom_events.yml"))

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

        # if the message is in a thread with an ongoing interaction, pass it to the interaction
        # message handler
        if isinstance(message.channel, Thread) and message.channel.id in self.active_threads:
            thread_interaction = self.active_threads[message.channel.id]
            await thread_interaction.on_message(message)
            if thread_interaction.completed:
                _logger.debug(f"Completed interaction on thread {message.channel.id}")
                await thread_interaction.finish()
                self.active_threads.pop(message.channel.id)
            return

        # otherwise check if the message is a command and pass it to the appropriate command handler
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

    async def on_reaction_added(self, reaction: Reaction, user: Member | User) -> None:
        # if the reaction is on a message in a thread with an active interaction, pass it to the
        # interaction reaction handler
        message = reaction.message
        if isinstance(message.channel, Thread) and message.channel.id in self.active_threads:
            thread_interaction = self.active_threads[message.channel.id]
            await thread_interaction.on_reaction(reaction)
            if thread_interaction.completed:
                _logger.debug(f"Completed interaction on thread {message.channel.id}")
                await thread_interaction.finish()
                self.active_threads.pop(message.channel.id)
            return

        # otherwise check if there are any registered handlers for reactions on this message
        if message.id in self.reaction_handlers:
            await self.reaction_handlers[message.id](reaction, user)

    @staticmethod
    def command(r: str) -> Callable[..., Any]:
        """
        Decorator for defining bot commands matching a given regex.

        After receiving a command, the bot will call the first @command function whose regex
        matches the given command.
        """

        def deco(f: Callable[..., Any]) -> Callable[..., Any]:
            _discord_bot_commands[re.compile(r, re.IGNORECASE)] = f
            return f

        return deco

    def affirm(self) -> str:
        return random.choice(AFFIRMATIONS)

    def thank(self) -> str:
        return random.choice(THANKS)


async def start() -> None:
    loop = asyncio.get_running_loop()

    intents = discord.Intents(
        messages=True, guild_messages=True, message_content=True, guilds=True, reactions=True
    )
    client = discord.Client(intents=intents, loop=loop)
    discord_bot: DiscordNotifierBot = DiscordNotifierBot(client)

    @client.event
    async def on_ready() -> None:
        _logger.info(f"We have logged in as {client.user}")

    @client.event
    async def on_message(message: Message) -> None:
        await discord_bot.on_message(message)

    @client.event
    async def on_reaction_add(reaction: Reaction, user: Member | User) -> None:
        await discord_bot.on_reaction_added(reaction, user)

    await client.start(settings.discord_token)
