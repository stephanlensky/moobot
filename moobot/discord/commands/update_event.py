from __future__ import annotations

import logging
from asyncio import create_task
from typing import TYPE_CHECKING, Awaitable, Callable

from discord import Interaction

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
            callback=get_update_event_callback(event),
            prefill=event,
        )
    )


def get_update_event_callback(
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

        event.id = original.id

        with Session(expire_on_commit=False) as session:
            session.query(MoobloomEvent).filter(MoobloomEvent.id == original.id).update(
                {
                    MoobloomEvent.name: event.name,
                    MoobloomEvent.create_channel: event.create_channel,
                    MoobloomEvent.channel_name: event.channel_name,
                    MoobloomEvent.start_date: event.start_date,
                    MoobloomEvent.start_time: event.start_time,
                    MoobloomEvent.end_date: event.end_date,
                    MoobloomEvent.end_time: event.end_time,
                    MoobloomEvent.location: event.location,
                    MoobloomEvent.description: event.description,
                    MoobloomEvent.url: event.url,
                    MoobloomEvent.image_url: event.image_url,
                    MoobloomEvent.out_of_sync: True,
                }
            )
            session.commit()

        create_task(initialize_events(bot))

        await interaction.response.send_message(
            f"{bot.affirm()} {interaction.user.mention}, I updated event {event.name} for you.",
            ephemeral=True,
        )

    return update_event_callback
