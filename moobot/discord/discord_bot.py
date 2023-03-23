from __future__ import annotations

import asyncio
import logging
import random
import re
import traceback
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Pattern

import discord
from apscheduler.triggers.interval import IntervalTrigger
from discord import (
    Interaction,
    Member,
    Message,
    PartialEmoji,
    RawReactionActionEvent,
    User,
    app_commands,
)

from moobot.db.session import Session
from moobot.discord.commands.create_event import create_event_cmd
from moobot.discord.commands.delete_event import delete_event_cmd
from moobot.discord.commands.update_event import update_event_cmd
from moobot.discord.event_option import event_autocomplete, get_event_from_option
from moobot.events import complete_unfinished_google_calendar_setups, initialize_events
from moobot.scheduler import get_async_scheduler, get_threadpool_scheduler
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
        self.tree = app_commands.CommandTree(client)
        self.command_prefix = command_prefix
        self.scheduler = get_async_scheduler()
        self.threadpool_scheduler = get_threadpool_scheduler()

        self.reaction_handlers: dict[int, ReactionHandler] = {}  # message ID -> reaction handler

    async def on_ready(self) -> None:
        self.scheduler.add_job(
            initialize_events,
            args=(self,),
            trigger=IntervalTrigger(seconds=60 * 5),
            next_run_time=datetime.now(),
        )
        self.threadpool_scheduler.add_job(
            complete_unfinished_google_calendar_setups,
            args=(self,),
            trigger=IntervalTrigger(seconds=10),
            next_run_time=datetime.now(),
        )
        for guild in self.client.guilds:
            _logger.info(f"Adding commands to guild {guild.name}")
            self.tree.copy_global_to(guild=guild)  # type: ignore

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

    @command(r"sync_commands")
    async def sync_commands(self, message: Message, command: re.Match) -> None:
        if message.guild is None:
            raise ValueError("Guild is none")
        _logger.info("Syncing commands")
        await self.tree.sync(guild=message.guild)  # type: ignore


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
        await discord_bot.on_ready()

    @client.event
    async def on_message(message: Message) -> None:
        await discord_bot.on_message(message)

    @client.event
    async def on_raw_reaction_add(payload: RawReactionActionEvent) -> None:
        await discord_bot.on_reaction_change(ReactionAction.ADDED, payload)

    @client.event
    async def on_raw_reaction_remove(payload: RawReactionActionEvent) -> None:
        await discord_bot.on_reaction_change(ReactionAction.REMOVED, payload)

    @discord_bot.tree.command(  # type: ignore
        name="create_event", description="Create a new event on the Moobloom calendar."
    )
    async def create_event(interaction: Interaction) -> None:
        _logger.info("Started create_event command")
        await create_event_cmd(discord_bot, interaction)

    @discord_bot.tree.command(  # type: ignore
        name="update_event", description="Update an existing event on the Moobloom calendar."
    )
    @app_commands.describe(event="The event to update")
    @app_commands.autocomplete(event=event_autocomplete)
    async def update_event(interaction: Interaction, event: str) -> None:
        _logger.info("Started update_event command")
        with Session() as session:
            db_event = get_event_from_option(session, event)
            if db_event is None:
                await interaction.response.send_message(
                    f"Sorry {interaction.user.mention}, I couldn't locate the event you selected."
                    " Please try again.",
                    ephemeral=True,
                )
                return

            await update_event_cmd(discord_bot, session, interaction, db_event)

    @discord_bot.tree.command(  # type: ignore
        name="delete_event", description="Permanently delete an event from the Moobloom calendar."
    )
    @app_commands.describe(event="The event to delete")
    @app_commands.autocomplete(event=event_autocomplete)
    async def delete_event(interaction: Interaction, event: str) -> None:
        with Session() as session:
            _logger.info("Started delete_event command")
            db_event = get_event_from_option(session, event)
            if db_event is None:
                await interaction.response.send_message(
                    f"Sorry {interaction.user.mention}, I couldn't locate the event you selected."
                    " Please try again.",
                    ephemeral=True,
                )
                return

            await delete_event_cmd(session, discord_bot, interaction, db_event)

    await client.start(settings.discord_token)
