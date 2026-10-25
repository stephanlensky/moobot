from __future__ import annotations

import logging
from asyncio import create_task
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TYPE_CHECKING

from discord import Interaction

from moobot.db.crud.events import get_event_by_id
from moobot.db.models import MoobloomEvent
from moobot.db.session import Session
from moobot.discord.views.event_modal import CreateEventModal
from moobot.events import initialize_events

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot


_logger = logging.getLogger(__name__)


async def update_event_cmd(bot: DiscordBot, interaction: Interaction, event: MoobloomEvent) -> None:
    await interaction.response.send_modal(
        CreateEventModal(
            bot,
            title="Update an event",
            callback=get_update_event_callback(event.id),
            prefill=event,
        )
    )


class UpdateEventError(Enum):
    EVENT_NOT_FOUND = "event_not_found"
    CHANNEL_NAME_CHANGED = "channel_name_changed"


def get_update_event_error_message(error: UpdateEventError, mention: str) -> str:
    match error:
        case UpdateEventError.EVENT_NOT_FOUND:
            return (
                f"Sorry {mention}, I couldn't locate the event you're updating. It may have been"
                " deleted."
            )
        case UpdateEventError.CHANNEL_NAME_CHANGED:
            return f"Sorry {mention}, updating event channel name is not currently supported."


def get_update_event_callback(
    event_id: int,
) -> Callable[[DiscordBot, Interaction, MoobloomEvent], Awaitable[None]]:
    async def update_event_callback(
        bot: DiscordBot, interaction: Interaction, event: MoobloomEvent
    ) -> None:
        result = await update_event(bot, event_id, event, interaction.user.id)
        if isinstance(result, UpdateEventError):
            await interaction.response.send_message(
                get_update_event_error_message(result, interaction.user.mention), ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"{bot.affirm()} {interaction.user.mention}, I updated event {result.name} for you.",
            ephemeral=True,
        )

    return update_event_callback


async def update_event(
    bot: DiscordBot, event_id: int, event: MoobloomEvent, user_id: int
) -> MoobloomEvent | UpdateEventError:
    with Session(expire_on_commit=False) as session:
        original = get_event_by_id(session, event_id)
        if original is None:
            return UpdateEventError.EVENT_NOT_FOUND

        if original.channel_name and original.channel_name != event.channel_name:
            return UpdateEventError.CHANNEL_NAME_CHANGED

        _logger.info(f"Updating event {original.name} ({original.id})")
        original.name = event.name
        original.create_channel = event.create_channel
        original.channel_name = event.channel_name
        original.start_date = event.start_date
        original.start_time = event.start_time
        original.end_date = event.end_date
        original.end_time = event.end_time
        original.location = event.location
        original.description = event.description
        original.url = event.url
        original.image_url = event.image_url
        original.out_of_sync = True
        original.updated_by = str(user_id)
        session.commit()

    create_task(initialize_events(bot))
    return original
