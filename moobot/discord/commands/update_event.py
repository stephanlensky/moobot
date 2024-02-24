from __future__ import annotations

import logging
from asyncio import create_task
from typing import TYPE_CHECKING, Awaitable, Callable

from discord import Interaction
from sqlalchemy.orm import Session

from moobot.db.models import MoobloomEvent
from moobot.discord.views.event_modal import CreateEventModal
from moobot.events import initialize_events

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot


_logger = logging.getLogger(__name__)


async def update_event_cmd(
    bot: DiscordBot, session: Session, interaction: Interaction, event: MoobloomEvent
) -> None:
    await interaction.response.send_modal(
        CreateEventModal(
            bot,
            title="Update an event",
            callback=get_update_event_callback(session, event),
            prefill=event,
        )
    )


def get_update_event_callback(
    session: Session,
    original: MoobloomEvent,
) -> Callable[[DiscordBot, Interaction, MoobloomEvent], Awaitable[None]]:
    async def update_event_callback(
        bot: DiscordBot, interaction: Interaction, event: MoobloomEvent
    ) -> None:
        if original.channel_name and original.channel_name != event.channel_name:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, updating event channel name is not currently"
                " supported.",
                ephemeral=True,
            )
            return

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
        original.updated_by = str(interaction.user.id)

        session.add(original)  # unclear why we need to do this
        session.commit()

        create_task(initialize_events(bot))

        await interaction.response.send_message(
            f"{bot.affirm()} {interaction.user.mention}, I updated event {event.name} for you.",
            ephemeral=True,
        )

    return update_event_callback
