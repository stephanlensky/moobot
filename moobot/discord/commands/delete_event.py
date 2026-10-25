from __future__ import annotations

import logging
from asyncio import create_task
from typing import TYPE_CHECKING

from discord import Interaction

from moobot.calendar_sync import handle_google_calendar_sync_on_rsvp
from moobot.db.crud.events import get_event_by_id
from moobot.db.models import MoobloomEvent, MoobloomEventAttendanceType
from moobot.db.session import Session
from moobot.discord.views.confirm_delete import ConfirmDelete
from moobot.events import delete_event_announcement, initialize_events

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot


_logger = logging.getLogger(__name__)


async def delete_event_cmd(bot: DiscordBot, interaction: Interaction, event: MoobloomEvent) -> None:
    confirm = ConfirmDelete()
    confirmation_message = await interaction.channel.send(  # type: ignore
        "Are you sure you want to continue? This will permanently delete event"
        f" {event.name} (id={event.id}).",
        view=confirm,
    )
    await interaction.response.defer(ephemeral=True)
    await confirm.wait()

    if not confirm.value:
        await interaction.followup.send("Operation cancelled.", ephemeral=True)
        return

    deleted_event = await delete_event(bot, event.id, interaction.user.id)
    await confirmation_message.delete()
    if deleted_event is None:
        await interaction.followup.send(
            f"Sorry {interaction.user.mention}, I couldn't locate the event you selected. It may"
            " have already been deleted.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        content=(
            f"{bot.affirm()} {interaction.user.mention}, I deleted event {deleted_event.name} from"
            " the calendar."
        ),
        ephemeral=True,
    )


async def delete_event(bot: DiscordBot, event_id: int, user_id: int) -> MoobloomEvent | None:
    with Session(expire_on_commit=False) as session:
        event = get_event_by_id(session, event_id)
        if event is None:
            return None

        _logger.info(f"Deleting event {event.name} ({event.id})")
        await delete_event_announcement(bot.client, event)
        for rsvp in event.rsvps:
            create_task(delete_google_calendar_event(bot, int(rsvp.user_id), event))

        event.deleted = True
        event.updated_by = str(user_id)
        session.commit()

    create_task(initialize_events(bot))
    return event


async def delete_google_calendar_event(bot: DiscordBot, user_id: int, event: MoobloomEvent) -> None:
    user = await bot.client.fetch_user(user_id)
    handle_google_calendar_sync_on_rsvp(bot.client, user, event, MoobloomEventAttendanceType.NO)
