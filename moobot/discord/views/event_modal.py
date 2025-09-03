from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Awaitable, Callable

from discord import Interaction, TextStyle
from discord.ui import Modal, TextInput

from moobot.db.models import MoobloomEvent
from moobot.util.date_parser import TimeAwareParserResult, time_aware_parser
from moobot.util.format import format_event_duration_for_event_modal

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot


_logger = logging.getLogger(__name__)

URL_REGEX = r"http(s)?://\S+"


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
        end = dataclasses.replace(start)  # copy object

    # this event is probably occurring next year
    if start.dt < datetime.now():
        _logger.info(
            "User specified start date appears to be in the past, automatically adding 1 year"
        )
        start.dt = start.dt.replace(year=start.dt.year + 1)
    if end.dt < datetime.now():
        _logger.info(
            "User specified end date appears to be in the past, automatically adding 1 year"
        )
        end.dt = end.dt.replace(year=end.dt.year + 1)

    if start.dt > end.dt:
        raise ValueError(
            f"Could not parse event time: start date ({start.dt}) is after end date ({end.dt})"
        )

    return EventTime(
        start_date=start.dt.date(),
        start_time=start.dt if start.has_time else None,
        end_date=end.dt.date(),
        end_time=end.dt if end.has_time and end != start else None,
    )


@dataclass
class EventDescriptionAndURLs:
    description: str | None
    url: str | None
    image_url: str | None


def _parse_event_description(raw_description: str | None) -> EventDescriptionAndURLs:
    if raw_description is None:
        return EventDescriptionAndURLs(description=None, url=None, image_url=None)

    url: str | None = None
    image_url: str | None = None
    parts = raw_description.split("\n")
    if re.match(rf"^{URL_REGEX}$", parts[0]):
        url = parts.pop(0)
        if re.match(rf"^{URL_REGEX}$", parts[0]):
            image_url = parts.pop(0)
    else:
        for part in parts:
            if m := re.match(rf"url:(?P<url>{URL_REGEX})", part):
                url = m.group("url")
            elif m := re.match(rf"image_url:(?P<url>{URL_REGEX})", part):
                image_url = m.group("url")

        if url:
            parts.remove(f"url:{url}")
        if image_url:
            parts.remove(f"image_url:{image_url}")

    description = "\n".join(parts)

    return EventDescriptionAndURLs(
        description=description or None,
        url=url,
        image_url=image_url,
    )


class CreateEventModal(Modal):
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

    def __init__(
        self,
        bot: DiscordBot,
        title: str,
        callback: Callable[[DiscordBot, Interaction, MoobloomEvent], Awaitable[None]],
        prefill: MoobloomEvent | None = None,
    ) -> None:
        self.bot = bot
        self.callback = callback

        super().__init__(title=title)

        if prefill is not None:
            self._prefill_fields(prefill)

    def _prefill_fields(self, event: MoobloomEvent) -> None:
        description_parts = (
            f"url:{event.url}" if event.url else None,
            f"image_url:{event.image_url}" if event.image_url else None,
            event.description,
        )

        for child in self.children:
            if not isinstance(child, TextInput):
                continue

            if child == self.name:
                child.default = event.name
            elif child == self.channel_name and event.channel_name:
                child.default = event.channel_name
            elif child == self.time:
                child.default = format_event_duration_for_event_modal(event)
            elif child == self.location and event.location:
                child.default = event.location
            elif child == self.description and any(description_parts):
                parts = (part for part in description_parts if part)
                child.default = "\n".join(parts)

    async def on_submit(self, interaction: Interaction) -> None:
        assert self.time.value is not None
        channel_name = self.channel_name.value or None
        description = self.description.value or None

        try:
            time = _parse_event_time(self.time.value)
        except ValueError as e:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, I didn't understand the time duration you"
                f" specified. Please try again.\n```{e}```",
                ephemeral=True,
            )
            return

        try:
            description_and_urls = _parse_event_description(description)
        except ValueError:
            await interaction.response.send_message(
                f"Sorry {interaction.user.mention}, I didn't understand the description you"
                " entered. Please try again.",
                ephemeral=True,
            )
            return

        event = MoobloomEvent(
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
            created_by=interaction.user.id,
        )

        await self.callback(self.bot, interaction, event)
