from __future__ import annotations

import logging
from asyncio import create_task
from typing import TYPE_CHECKING

from discord import Interaction

from moobot.db.models import MoobloomEvent
from moobot.db.session import Session
from moobot.discord.views.event_modal import CreateEventModal
from moobot.events import initialize_events

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot


_logger = logging.getLogger(__name__)


async def create_event_cmd(bot: DiscordBot, interaction: Interaction) -> None:
    await interaction.response.send_modal(
        CreateEventModal(
            bot,
            title="Create a new event",
            callback=create_event_callback,
        )
    )


async def create_event_callback(
    bot: DiscordBot, interaction: Interaction, event: MoobloomEvent
) -> None:
    with Session(expire_on_commit=False) as session:
        _logger.info(f"Adding event {event.name}")
        session.add(event)
        session.commit()

    create_task(initialize_events(bot))

    await interaction.response.send_message(
        f"{bot.affirm()} {interaction.user.mention}, I added a new event"
        f" {event.name} to the calendar.",
        ephemeral=True,
    )
