from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import discord
from discord import Interaction, Message

from moobot.agent.notes import get_calendar_sync_note, get_delete_cancelled_note, get_event_note
from moobot.calendar_sync import (
    CALENDAR_SYNC_LABELS,
    disable_calendar_sync,
    enable_calendar_sync,
)
from moobot.constants import (
    AGENT_ACTION_ALREADY_USED_MESSAGE,
    AGENT_ACTION_VIEW_TIMEOUT,
    AGENT_BUTTON_ATTEMPT_TTL,
    AGENT_BUTTON_EASTER_EGG_ATTEMPTS,
    AGENT_CALENDAR_SYNC_DM_FAILED_MESSAGE,
    AGENT_CALENDAR_SYNC_STARTED_MESSAGES,
    AGENT_CALENDAR_SYNC_STOPPED_MESSAGES,
    AGENT_EVENT_CREATED_MESSAGES,
    AGENT_EVENT_DELETE_CANCELLED_MESSAGES,
    AGENT_EVENT_DELETED_MESSAGES,
    AGENT_EVENT_UPDATED_MESSAGES,
    AGENT_NOT_YOUR_BUTTON_MESSAGES,
    AGENT_REPLY_ALLOWED_MENTIONS,
)
from moobot.db.crud.events import get_event_by_id
from moobot.db.models import GoogleCalendarType, MoobloomEvent
from moobot.db.session import Session
from moobot.discord.commands.create_event import create_event
from moobot.discord.commands.delete_event import delete_event
from moobot.discord.commands.update_event import (
    UpdateEventError,
    get_update_event_error_message,
    update_event,
)
from moobot.discord.views.event_modal import CreateEventModal, EventTime

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot

_logger = logging.getLogger(__name__)

CALENDAR_SYNC_NAMES = {
    GoogleCalendarType.EVENTS: "event sync",
    GoogleCalendarType.BIRTHDAYS: "birthday sync",
}


@dataclass
class EventFields:
    name: str | None = None
    time: EventTime | None = None
    location: str | None = None
    channel_name: str | None = None
    description: str | None = None
    url: str | None = None
    image_url: str | None = None


def get_event_prefill(fields: EventFields, event: MoobloomEvent | None = None) -> MoobloomEvent:
    base = event if event is not None else MoobloomEvent()
    return MoobloomEvent(
        name=fields.name or base.name,
        channel_name=fields.channel_name or base.channel_name,
        start_date=fields.time.start_date if fields.time else base.start_date,
        start_time=fields.time.start_time if fields.time else base.start_time,
        end_date=fields.time.end_date if fields.time else base.end_date,
        end_time=fields.time.end_time if fields.time else base.end_time,
        location=fields.location or base.location,
        description=fields.description or base.description,
        url=fields.url or base.url,
        image_url=fields.image_url or base.image_url,
    )


class ButtonAttemptCounter:
    def __init__(
        self,
        ttl: timedelta = AGENT_BUTTON_ATTEMPT_TTL,
        get_time: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl = ttl.total_seconds()
        self.get_time = get_time
        self.attempts: dict[int, tuple[int, float]] = {}

    def prune(self, now: float) -> None:
        self.attempts = {
            user_id: (count, last_attempt_at)
            for user_id, (count, last_attempt_at) in self.attempts.items()
            if now - last_attempt_at < self.ttl
        }

    def add_attempt(self, user_id: int) -> int:
        now = self.get_time()
        self.prune(now)
        count = self.attempts.get(user_id, (0, now))[0] + 1
        self.attempts[user_id] = (count, now)
        return count

    def reset(self, user_id: int) -> None:
        self.prune(self.get_time())
        self.attempts.pop(user_id, None)


button_attempt_counter = ButtonAttemptCounter()


def get_not_your_button_message(attempts: int) -> str:
    phrases = next(
        phrases
        for min_attempts, phrases in reversed(AGENT_NOT_YOUR_BUTTON_MESSAGES)
        if attempts >= min_attempts
    )
    return random.choice(phrases)


class AgentActionView(discord.ui.View):
    def __init__(
        self, bot: DiscordBot, author_id: int, original_message: Message, label: str
    ) -> None:
        super().__init__(timeout=AGENT_ACTION_VIEW_TIMEOUT.total_seconds())
        self.bot = bot
        self.author_id = author_id
        self.original_message = original_message
        self.label = label
        self.message: Message | None = None
        self.used = False

    async def interaction_check(self, interaction: Interaction, /) -> bool:
        if interaction.user.id == self.author_id:
            return True
        attempts = button_attempt_counter.add_attempt(interaction.user.id)
        if attempts >= AGENT_BUTTON_EASTER_EGG_ATTEMPTS:
            _logger.info(
                f"User {interaction.user.id} clicked someone else's buttons {attempts} times,"
                f" running the easter egg for view {self.label}"
            )
            button_attempt_counter.reset(interaction.user.id)
            return True
        await interaction.response.send_message(
            get_not_your_button_message(attempts), ephemeral=True
        )
        return False

    def disable_buttons(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        self.stop()

    async def update_message(self) -> None:
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            _logger.warning(f"Failed to update message {self.message.id} for view {self.label}")

    async def set_used(self) -> None:
        self.used = True
        self.disable_buttons()
        await self.update_message()

    async def send_confirmation(
        self, interaction: Interaction, phrases: list[str], event_name: str
    ) -> None:
        text = random.choice(phrases).format(name=event_name, mention=interaction.user.mention)
        try:
            await self.original_message.reply(text, allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS)
        except discord.HTTPException:
            _logger.warning(
                f"Failed to reply to message {self.original_message.id} for view {self.label}"
            )

    async def add_transcript_note(self, text: str) -> None:
        await self.bot.agent_worker.add_transcript_note(self.original_message.channel.id, text)

    async def on_timeout(self) -> None:
        self.disable_buttons()
        await self.update_message()

    async def on_error(
        self, interaction: Interaction, error: Exception, item: discord.ui.Item[Any], /
    ) -> None:
        _logger.error(f"Error in view {self.label} for item {item}", exc_info=error)


class CreateEventView(AgentActionView):
    def __init__(
        self, bot: DiscordBot, author_id: int, original_message: Message, fields: EventFields
    ) -> None:
        label = f"Create event: {fields.name}" if fields.name else "Create event"
        super().__init__(bot, author_id, original_message, label)
        self.fields = fields

    @discord.ui.button(label="Open event form", style=discord.ButtonStyle.primary)
    async def open_form(self, interaction: Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(
            CreateEventModal(
                self.bot,
                title="Create a new event",
                callback=self.submit_form,
                prefill=get_event_prefill(self.fields),
            )
        )

    async def submit_form(
        self, bot: DiscordBot, interaction: Interaction, event: MoobloomEvent
    ) -> None:
        if self.used:
            await interaction.response.send_message(
                AGENT_ACTION_ALREADY_USED_MESSAGE, ephemeral=True
            )
            return
        event = await create_event(bot, event)
        await interaction.response.defer()
        await self.set_used()
        await self.send_confirmation(interaction, AGENT_EVENT_CREATED_MESSAGES, event.name)
        await self.add_transcript_note(get_event_note(interaction.user, "created", event))


class UpdateEventView(AgentActionView):
    def __init__(
        self,
        bot: DiscordBot,
        author_id: int,
        original_message: Message,
        event_id: int,
        event_name: str,
        fields: EventFields,
    ) -> None:
        super().__init__(bot, author_id, original_message, f"Update event: {event_name}")
        self.event_id = event_id
        self.fields = fields

    @discord.ui.button(label="Open event form", style=discord.ButtonStyle.primary)
    async def open_form(self, interaction: Interaction, button: discord.ui.Button) -> None:
        with Session() as session:
            event = get_event_by_id(session, self.event_id)
            prefill = get_event_prefill(self.fields, event) if event is not None else None
        if prefill is None:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, I couldn't locate that event. It may have been"
                " deleted.",
                ephemeral=True,
            )
            await self.set_used()
            return

        await interaction.response.send_modal(
            CreateEventModal(
                self.bot, title="Update an event", callback=self.submit_form, prefill=prefill
            )
        )

    async def submit_form(
        self, bot: DiscordBot, interaction: Interaction, event: MoobloomEvent
    ) -> None:
        if self.used:
            await interaction.response.send_message(
                AGENT_ACTION_ALREADY_USED_MESSAGE, ephemeral=True
            )
            return
        result = await update_event(bot, self.event_id, event, interaction.user.id)
        if isinstance(result, UpdateEventError):
            await interaction.response.send_message(
                get_update_event_error_message(result, interaction.user.mention), ephemeral=True
            )
            return
        await interaction.response.defer()
        await self.set_used()
        await self.send_confirmation(interaction, AGENT_EVENT_UPDATED_MESSAGES, result.name)
        await self.add_transcript_note(get_event_note(interaction.user, "updated", result))


class DeleteEventView(AgentActionView):
    def __init__(
        self,
        bot: DiscordBot,
        author_id: int,
        original_message: Message,
        event_id: int,
        event_name: str,
    ) -> None:
        super().__init__(bot, author_id, original_message, f"Delete event: {event_name}")
        self.event_id = event_id
        self.event_name = event_name

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.red)
    async def delete(self, interaction: Interaction, button: discord.ui.Button) -> None:
        self.used = True
        self.disable_buttons()
        await interaction.response.edit_message(view=self)
        event = await delete_event(self.bot, self.event_id, interaction.user.id)
        if event is None:
            await interaction.followup.send(
                f"Sorry {interaction.user.mention}, I couldn't locate that event. It may have"
                " already been deleted.",
                ephemeral=True,
            )
            return
        await self.send_confirmation(interaction, AGENT_EVENT_DELETED_MESSAGES, event.name)
        await self.add_transcript_note(get_event_note(interaction.user, "deleted", event))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: Interaction, button: discord.ui.Button) -> None:
        self.used = True
        self.disable_buttons()
        await interaction.response.edit_message(view=self)
        await self.send_confirmation(
            interaction, AGENT_EVENT_DELETE_CANCELLED_MESSAGES, self.event_name
        )
        await self.add_transcript_note(
            get_delete_cancelled_note(interaction.user, self.event_id, self.event_name)
        )


class CalendarSyncView(AgentActionView):
    confirmation_messages: list[str]
    note_action: str

    def __init__(
        self,
        bot: DiscordBot,
        author_id: int,
        original_message: Message,
        calendar_type: GoogleCalendarType,
        label: str,
    ) -> None:
        super().__init__(bot, author_id, original_message, f"{label}: {calendar_type.value}")
        self.calendar_type = calendar_type

    async def set_calendar_sync(self, interaction: Interaction) -> None:
        raise NotImplementedError

    async def handle_click(self, interaction: Interaction) -> None:
        self.used = True
        self.disable_buttons()
        await interaction.response.edit_message(view=self)
        try:
            await self.set_calendar_sync(interaction)
        except discord.Forbidden:
            _logger.warning(f"Failed to DM user {interaction.user.id} for view {self.label}")
            await interaction.followup.send(AGENT_CALENDAR_SYNC_DM_FAILED_MESSAGE, ephemeral=True)
            return
        await self.send_confirmation(
            interaction, self.confirmation_messages, CALENDAR_SYNC_NAMES[self.calendar_type]
        )
        await self.add_transcript_note(
            get_calendar_sync_note(
                interaction.user, self.note_action, CALENDAR_SYNC_LABELS[self.calendar_type]
            )
        )


class StartCalendarSyncView(CalendarSyncView):
    confirmation_messages = AGENT_CALENDAR_SYNC_STARTED_MESSAGES
    note_action = "clicked the button and got a DM to finish setting up"

    def __init__(
        self,
        bot: DiscordBot,
        author_id: int,
        original_message: Message,
        calendar_type: GoogleCalendarType,
    ) -> None:
        super().__init__(bot, author_id, original_message, calendar_type, "Start calendar sync")

    async def set_calendar_sync(self, interaction: Interaction) -> None:
        await enable_calendar_sync(interaction.user, self.calendar_type)

    @discord.ui.button(label="Set up sync", style=discord.ButtonStyle.primary)
    async def start(self, interaction: Interaction, button: discord.ui.Button) -> None:
        await self.handle_click(interaction)


class StopCalendarSyncView(CalendarSyncView):
    confirmation_messages = AGENT_CALENDAR_SYNC_STOPPED_MESSAGES
    note_action = "clicked the button and turned off"

    def __init__(
        self,
        bot: DiscordBot,
        author_id: int,
        original_message: Message,
        calendar_type: GoogleCalendarType,
    ) -> None:
        super().__init__(bot, author_id, original_message, calendar_type, "Stop calendar sync")

    async def set_calendar_sync(self, interaction: Interaction) -> None:
        await disable_calendar_sync(
            interaction.user, self.calendar_type, notify_if_not_enabled=True
        )

    @discord.ui.button(label="Stop sync", style=discord.ButtonStyle.red)
    async def stop_sync(self, interaction: Interaction, button: discord.ui.Button) -> None:
        await self.handle_click(interaction)
