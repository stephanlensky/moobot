from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord import Interaction

from moobot.db.models import MoobloomEvent, MoobloomEventRSVP
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
    await confirm.wait()

    if confirm.value:
        await delete_event_announcement(bot.client, event)
        with Session(expire_on_commit=False) as session:
            session.query(MoobloomEventRSVP).filter(MoobloomEventRSVP.event_id == event.id).delete()
            session.delete(event)
            session.commit()

        await confirmation_message.delete()
        await interaction.response.send_message(
            f"{bot.affirm()} {interaction.user.mention}, I deleted event {event.name} from the"
            " calendar.",
            ephemeral=True,
        )
        await initialize_events(bot)
    else:
        await interaction.response.send_message(
            "Operation cancelled.",
            ephemeral=True,
        )
