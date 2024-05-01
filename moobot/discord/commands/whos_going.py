from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord import Interaction
from sqlalchemy.orm import Session

from moobot.db.models import MoobloomEvent, MoobloomEventAttendanceType
from moobot.util.discord import mention

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot


_logger = logging.getLogger(__name__)


async def whos_going_cmd(
    session: Session, bot: DiscordBot, interaction: Interaction, event: MoobloomEvent
) -> None:
    rsvps: dict[str, list[str]] = {
        attendance_type: [] for attendance_type in MoobloomEventAttendanceType
    }
    for rsvp in event.rsvps:
        rsvps[rsvp.attendance_type].append(rsvp.user_id)

    formatted_rsvps: dict[str, str] = {}
    for attendance_type, attending_users in rsvps.items():
        if not attending_users:
            formatted_rsvps[attendance_type] = "None"
        else:
            formatted_rsvps[attendance_type] = "\n".join(
                [f"- {mention(user_id)}" for user_id in rsvps[attendance_type]]
            )

    going = f"**Going:**\n{formatted_rsvps[MoobloomEventAttendanceType.YES]}"
    maybe = f"**Maybe:**\n{formatted_rsvps[MoobloomEventAttendanceType.MAYBE]}"
    not_going = f"**Not going:**\n{formatted_rsvps[MoobloomEventAttendanceType.NO]}"
    response = (
        f"Sure {interaction.user.mention}, here is the full list of attendees for **{event.name}**:"
        f"\n\n{going}\n\n{maybe}\n\n{not_going}"
    )
    await interaction.response.send_message(response, ephemeral=True)
