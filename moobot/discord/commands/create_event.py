from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

from discord import Interaction, TextStyle
from discord.ui import Modal, TextInput

from moobot.db.models import MoobloomEvent
from moobot.db.session import Session
from moobot.events import initialize_events
from moobot.util.date_parser import TimeAwareParserResult, time_aware_parser

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot


@dataclass
class EventTime:
    start_date: date
    start_time: datetime | None
    end_date: date
    end_time: datetime | None


def _parse_event_time(raw_time: str) -> EventTime:
    time_parts = raw_time.split(" to ")
    if len(time_parts) > 2:
        raise ValueError("Could not parse event time: too many parts")

    start: TimeAwareParserResult = time_aware_parser.parse(time_parts[0])  # type: ignore

    if len(time_parts) == 2:
        end: TimeAwareParserResult = time_aware_parser.parse(time_parts[1])  # type: ignore
        # support strings like "9/21 7pm to 10pm"
        if not end.has_date:
            end.dt = end.dt.replace(year=start.dt.year, month=start.dt.month, day=start.dt.day)
    else:
        end = start

    return EventTime(
        start_date=start.dt.date(),
        start_time=start.dt if start.has_time else None,
        end_date=end.dt.date(),
        end_time=end.dt if end.has_time else None,
    )


@dataclass
class EventDescriptionAndURLs:
    description: str | None
    url: str | None
    image_url: str | None


def _parse_event_description(raw_description: str | None) -> EventDescriptionAndURLs:
    if raw_description is None:
        return EventDescriptionAndURLs(description=None, url=None, image_url=None)

    m = re.match(
        r"((?P<event_url>http(s)?://\S+)\s((?P<image_url>http(s)?://\S+)\s)?)?(?P<description>.+)",
        raw_description,
        flags=re.S,
    )
    if m is None:
        raise ValueError("Could not parse description")
    return EventDescriptionAndURLs(
        description=m.group("description"), url=m.group("event_url"), image_url=m.group("image_url")
    )


class CreateEventModal(Modal, title="Create a new event"):
    name: TextInput = TextInput(label="Name", placeholder="Name of the event", required=True)
    channel_name: TextInput = TextInput(
        label="Channel name",
        placeholder="Name of the event channel, if one should be created",
        required=False,
    )
    time: TextInput = TextInput(
        label="Time",
        placeholder='ex. "September 21" or "9/21 7pm to 10pm"',
        required=True,
    )
    location: TextInput = TextInput(
        label="Location", placeholder="Location of the event", required=False
    )
    description: TextInput = TextInput(
        label="Description and URLs",
        style=TextStyle.paragraph,
        placeholder=(
            "Description for the event. To set event URLs, paste event and/or image URLs before the"
            " description."
        ),
        required=False,
    )

    def __init__(self, bot: DiscordBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: Interaction) -> None:
        assert self.time.value is not None
        channel_name = self.channel_name.value or None
        description = self.description.value or None

        try:
            time = _parse_event_time(self.time.value)
        except ValueError:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, I didn't understand the time duration you"
                " specified. Please try creating the event again.",
                ephemeral=True,
            )
            return

        try:
            description_and_urls = _parse_event_description(description)
        except ValueError:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, I didn't understand the description you"
                " entered. Please try creating the event again.",
                ephemeral=True,
            )
            return

        with Session(expire_on_commit=False) as session:
            session.add(
                MoobloomEvent(
                    name=self.name.value,
                    create_channel=channel_name is not None,
                    channel_name=channel_name,
                    start_date=time.start_date,
                    start_time=time.start_time,
                    end_date=time.end_date,
                    end_time=time.end_time,
                    location=self.location.value,
                    description=description_and_urls.description,
                    url=description_and_urls.url,
                    image_url=description_and_urls.image_url,
                )
            )
            session.commit()

        await initialize_events(self.bot)

        await interaction.response.send_message(
            f"{self.bot.affirm()} {interaction.user.mention}, I added a new event"
            f" {self.name.value} to the calendar.",
            ephemeral=True,
        )
