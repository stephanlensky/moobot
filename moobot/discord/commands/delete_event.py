from __future__ import annotations

import logging
from asyncio import create_task
from typing import TYPE_CHECKING

from discord import Interaction
from sqlalchemy.orm import Session

from moobot.db.models import MoobloomEvent, MoobloomEventAttendanceType, MoobloomEventRSVP
from moobot.discord.views.confirm_delete import ConfirmDelete
from moobot.events import (
    delete_event_announcement,
    handle_google_calendar_sync_on_rsvp,
    initialize_events,
)

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot


_logger = logging.getLogger(__name__)


async def delete_event_cmd(
    session: Session, bot: DiscordBot, interaction: Interaction, event: MoobloomEvent
) -> None:
    confirm = ConfirmDelete()
    confirmation_message = await interaction.channel.send(  # type: ignore
        "Are you sure you want to continue? This will permanently delete event"
        f" {event.name} (id={event.id}).",
        view=confirm,
    )
    await interaction.response.defer(ephemeral=True)
    await confirm.wait()

    if confirm.value:
        await delete_event_announcement(bot.client, event)
        for rsvp in event.rsvps:
            create_task(delete_google_calendar_event(bot, int(rsvp.user_id), event))

        session.query(MoobloomEventRSVP).filter(MoobloomEventRSVP.event_id == event.id).delete()
        session.delete(event)
        session.commit()

        await confirmation_message.delete()
        await interaction.followup.send(
            content=(
                f"{bot.affirm()} {interaction.user.mention}, I deleted event {event.name} from the"
                " calendar."
            ),
            ephemeral=True,
        )

        await initialize_events(bot)
    else:
        await interaction.response.send_message(
            "Operation cancelled.",
            ephemeral=True,
        )


async def delete_google_calendar_event(bot: DiscordBot, user_id: int, event: MoobloomEvent) -> None:
    user = await bot.client.fetch_user(user_id)
    handle_google_calendar_sync_on_rsvp(user, event, MoobloomEventAttendanceType.NO)
