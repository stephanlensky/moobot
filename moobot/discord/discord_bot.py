from __future__ import annotations

import logging
import random
from collections.abc import Callable, Coroutine
from enum import Enum
from typing import Any

import discord
from apscheduler.triggers.interval import IntervalTrigger
from discord import (
    AllowedMentions,
    Interaction,
    Member,
    Message,
    PartialEmoji,
    RawReactionActionEvent,
    User,
    app_commands,
)

from moobot.agent.history import is_bot_mentioned
from moobot.agent.worker import AgentWorker
from moobot.calendar_sync import complete_unfinished_google_calendar_setups
from moobot.db.session import Session
from moobot.discord.commands.agent import agent_group
from moobot.discord.commands.create_event import create_event_cmd
from moobot.discord.commands.delete_event import delete_event_cmd
from moobot.discord.commands.update_event import update_event_cmd
from moobot.discord.commands.whos_going import whos_going_cmd
from moobot.discord.event_option import event_autocomplete, get_event_from_option
from moobot.events import initialize_events
from moobot.scheduler import get_async_scheduler, get_threadpool_scheduler
from moobot.settings import get_settings
from moobot.util.time import now as local_now

settings = get_settings()
_logger = logging.getLogger(__name__)

AFFIRMATIONS = ["Okay", "Sure", "Sounds good", "No problem", "Roger that", "Got it"]


class ReactionAction(str, Enum):
    ADDED = "added"
    REMOVED = "removed"


ReactionHandler = Callable[[ReactionAction, PartialEmoji, User | Member], Coroutine[None, Any, Any]]


class DiscordBot:
    def __init__(self, client: discord.Client) -> None:
        self.client = client
        self.tree = app_commands.CommandTree(client)
        self.scheduler = get_async_scheduler()
        self.threadpool_scheduler = get_threadpool_scheduler()

        self.reaction_handlers: dict[int, ReactionHandler] = {}  # message ID -> reaction handler
        self.agent_worker = AgentWorker(self)

    async def on_ready(self) -> None:
        self.agent_worker.start_queued_workers()
        self.scheduler.add_job(
            initialize_events,
            id="initialize_events",
            replace_existing=True,
            args=(self,),
            trigger=IntervalTrigger(seconds=60 * 5),
            next_run_time=local_now(),
        )
        self.threadpool_scheduler.add_job(
            complete_unfinished_google_calendar_setups,
            id="complete_unfinished_google_calendar_setups",
            replace_existing=True,
            args=(self,),
            trigger=IntervalTrigger(seconds=10),
            next_run_time=local_now(),
        )
        for guild in self.client.guilds:
            _logger.info(f"Adding commands to guild {guild.name}")
            self.tree.copy_global_to(guild=guild)  # type: ignore
            await self.tree.sync(guild=guild)  # type: ignore

    async def on_message(self, message: Message) -> None:
        if message.author.bot or self.client.user is None:
            return

        if is_bot_mentioned(message, self.client.user):
            self.agent_worker.queue_turn(message)

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

    def affirm(self) -> str:
        return random.choice(AFFIRMATIONS)


async def start() -> None:
    intents = discord.Intents(
        messages=True,
        guild_messages=True,
        message_content=True,
        guilds=True,
        reactions=True,
        members=True,
    )
    client = discord.Client(intents=intents, allowed_mentions=AllowedMentions(everyone=False))
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

    discord_bot.tree.add_command(agent_group)

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
                    (
                        f"Sorry {interaction.user.mention}, I couldn't locate the event you"
                        " selected. Please try again."
                    ),
                    ephemeral=True,
                )
                return

            await update_event_cmd(discord_bot, interaction, db_event)

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
                    (
                        f"Sorry {interaction.user.mention}, I couldn't locate the event you"
                        " selected. Please try again."
                    ),
                    ephemeral=True,
                )
                return

            await delete_event_cmd(discord_bot, interaction, db_event)

    @discord_bot.tree.command(  # type: ignore
        name="whos_going", description="Check who is currently RSVP'd to a given event."
    )
    @app_commands.describe(event="The event to check RSVPs for")
    @app_commands.autocomplete(event=event_autocomplete)
    async def whos_going(interaction: Interaction, event: str) -> None:
        with Session() as session:
            _logger.info("Started whos_going command")
            db_event = get_event_from_option(session, event)
            if db_event is None:
                await interaction.response.send_message(
                    (
                        f"Sorry {interaction.user.mention}, I couldn't locate the event you"
                        " selected. Please try again."
                    ),
                    ephemeral=True,
                )
                return

            await whos_going_cmd(session, discord_bot, interaction, db_event)

    await client.start(settings.discord_token)
