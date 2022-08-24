from __future__ import annotations

import calendar
import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

import discord
import yaml
from discord import (
    Embed,
    Emoji,
    Member,
    Message,
    PartialEmoji,
    PermissionOverwrite,
    TextChannel,
    User,
)
from discord.utils import get

from moobot.db.models import MoobloomEvent, MoobloomEventAttendanceType, MoobloomEventRSVP
from moobot.db.session import Session
from moobot.settings import get_settings
from moobot.util.format import format_event_duration, format_single_event_for_calendar

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot, ReactionAction

settings = get_settings()

_logger = logging.getLogger(__name__)


async def initialize_events(bot: DiscordBot) -> None:
    await load_events_from_file(bot.client, Path("moobloom_events.yml"))
    await send_event_announcements(bot.client)
    await create_event_channels(bot.client)
    await update_calendar_message(bot.client)
    await add_reaction_handlers(bot)


def read_events_from_file(path: Path) -> list[MoobloomEvent]:
    with path.open("r", encoding="utf-8") as f:
        events = yaml.safe_load(f)["events"]

    # there is a typing bug with parse_obj in the current version of sqlmodel
    return [MoobloomEvent.parse_obj(event) for event in events]  # type: ignore


def get_calendar_channel(client: discord.Client) -> TextChannel:
    calendar_channel = client.get_channel(settings.calendar_channel_id)
    if calendar_channel is None:
        raise ValueError("Calendar channel does not exist")
    if not isinstance(calendar_channel, TextChannel):
        raise ValueError(f"Calendar channel has bad type {type(calendar_channel)}")
    return calendar_channel


def get_announcement_channel(client: discord.Client) -> TextChannel:
    announcement_channel = client.get_channel(settings.event_announce_channel_id)
    if announcement_channel is None:
        raise ValueError("Announcement channel does not exist")
    if not isinstance(announcement_channel, TextChannel):
        raise ValueError(f"Announcement channel has bad type {type(announcement_channel)}")
    return announcement_channel


def get_custom_emoji_by_name(client: discord.Client, emoji: str) -> Emoji:
    return next(e for e in client.emojis if e.name == emoji)


async def load_events_from_file(_client: discord.Client, path: Path) -> None:
    with Session() as session:
        existing_event_names = {n[0] for n in session.query(MoobloomEvent.name).all()}

    new_events = 0
    for event in read_events_from_file(path):
        if event.name in existing_event_names:
            continue

        with Session() as session:
            session.add(event)
            session.commit()

            _logger.info(f"Found event {event.name}")
        new_events += 1

    _logger.info(f"Loaded {new_events} events from file")


async def send_event_announcements(client: discord.Client) -> None:
    with Session(expire_on_commit=False) as session:
        events: list[MoobloomEvent] = (
            session.query(MoobloomEvent)
            .filter(
                MoobloomEvent.announcement_message_id  # pylint: disable=singleton-comparison
                == None
            )
            .all()
        )

    for event in events:
        await send_event_announcement(client, event)


async def create_event_channels(client: discord.Client) -> None:
    with Session(expire_on_commit=False) as session:
        events: list[MoobloomEvent] = (
            session.query(MoobloomEvent)
            .filter(MoobloomEvent.channel_id == None)  # pylint: disable=singleton-comparison
            .all()
        )

    for event in events:
        await create_event_channel(client, event)


async def get_calendar_message(
    client: discord.Client, calendar_channel: TextChannel
) -> Message | None:
    calendar_message: Message | None = None
    async for message in calendar_channel.history():
        if client.user is not None and message.author.id == client.user.id:
            calendar_message = message
            break

    return calendar_message


async def update_calendar_message(client: discord.Client) -> None:
    calendar_channel = get_calendar_channel(client)
    announcement_channel = get_announcement_channel(client)

    with Session() as session:
        events: list[MoobloomEvent] = (
            session.query(MoobloomEvent)
            .filter(MoobloomEvent.end_date >= date.today())
            .order_by(MoobloomEvent.start_date)
            .all()
        )

    events_by_month_and_year: dict[tuple[int, int], list[MoobloomEvent]] = {}
    for event in events:
        month_and_year = (event.start_date.month, event.start_date.year)
        if month_and_year not in events_by_month_and_year:
            events_by_month_and_year[month_and_year] = []
        events_by_month_and_year[month_and_year].append(event)

    formatted_events_by_month_and_year: dict[tuple[int, int], str] = {}
    for (month, year), events in events_by_month_and_year.items():
        formatted_events_by_month_and_year[(month, year)] = "\n".join(
            [format_single_event_for_calendar(e) for e in events]
        )

    months_sections = "\n\n".join(
        [
            f"**{calendar.month_name[month]} {year}:**\n{events}"
            for (month, year), events in formatted_events_by_month_and_year.items()
        ]
    )

    intro_section = (
        "Welcome to the Moobloom Event calendar! A full list of upcoming events is available"
        " below.\nIn order to reduce notification spam, each event has a private channel for"
        f" discussion and planning. To gain access, RSVP in {announcement_channel.mention}."
    )
    all_events_react_emoji = get_custom_emoji_by_name(
        client, settings.get_all_event_channels_react_emoji_name
    )
    react_section = (
        "To automatically gain access to all new event channels (and accept the consequences of"
        f" recieving a ton of notifications), react with {all_events_react_emoji}."
    )

    message_content = (
        f"{intro_section}\n\n**Moobloom Event Calendar:**\n\n{months_sections}\n\n*{react_section}*"
    )

    calendar_message = await get_calendar_message(client, calendar_channel)
    if calendar_message is None:
        _logger.info("Calendar message not found, sending new calendar")
        calendar_message = await calendar_channel.send(content=message_content)
        await calendar_message.add_reaction(all_events_react_emoji)
    elif message_content != calendar_message.content:
        _logger.info("Updating calendar message")
        await calendar_message.edit(content=message_content)
    else:
        _logger.info("Calendar message is up to date, doing nothing")


async def send_event_announcement(client: discord.Client, event: MoobloomEvent) -> None:
    _logger.info(f"Announcing event {event.name}")

    announcement_channel = get_announcement_channel(client)

    event_duration = format_event_duration(
        event.start_date, event.start_time, event.end_date, event.end_time
    )

    if event.location:
        description_content = f"**{event_duration} - {event.location}**"
    else:
        description_content = f"**{event_duration}**"
    if event.description:
        description_content = f"{description_content}\n{event.description}"

    description_content = (
        f"{description_content}\n*To RSVP and gain access to the event channel, react with"
        f" {settings.rsvp_yes_emoji} (going) or {settings.rsvp_maybe_emoji} (maybe).\nIf you are"
        f" not going, react with {settings.rsvp_no_emoji}.*"
    )

    embed = Embed(title=event.name, url=event.url, description=description_content)
    if event.image_url:
        embed.set_image(url=event.image_url)
    if event.thumbnail_url:
        embed.set_thumbnail(url=event.image_url)
    message = await announcement_channel.send(embed=embed)
    await message.add_reaction(settings.rsvp_yes_emoji)
    await message.add_reaction(settings.rsvp_maybe_emoji)
    await message.add_reaction(settings.rsvp_no_emoji)

    with Session() as session:
        session.add(event)
        event.announcement_message_id = str(message.id)
        session.commit()


async def create_event_channel(client: discord.Client, event: MoobloomEvent) -> None:
    guild = get_announcement_channel(client).guild
    category = get(guild.categories, name=settings.active_events_category_name)
    if category is None:
        raise ValueError(f"category {settings.active_events_category_name} not found")
    all_events_role = get(guild.roles, name=settings.all_events_role_name)
    if all_events_role is None:
        raise ValueError(f"role {settings.all_events_role_name} not found")

    overwrites = {
        guild.default_role: PermissionOverwrite(read_messages=False),
        all_events_role: PermissionOverwrite(read_messages=True),
    }
    channel = await guild.create_text_channel(
        name=event.channel_name, category=category, overwrites=overwrites  # type: ignore
    )
    with Session() as session:
        session.add(event)
        event.channel_id = str(channel.id)
        session.commit()
        _logger.info(f"Created channel {event.channel_name} for event {event.name}")


async def add_calendar_reaction_handler(bot: DiscordBot) -> None:
    calendar_channel = get_calendar_channel(bot.client)
    calendar_message = await get_calendar_message(bot.client, calendar_channel)
    all_events_react_emoji = get_custom_emoji_by_name(
        bot.client, settings.get_all_event_channels_react_emoji_name
    )

    if calendar_message is None:
        raise ValueError("calendar message not yet sent")

    async def on_calendar_message_reaction(
        action: ReactionAction, emoji: PartialEmoji, user: Member | User
    ) -> None:
        if not isinstance(user, Member):
            raise ValueError("bot must be used on a server")
        if emoji.id != all_events_react_emoji.id:
            return

        role = get(user.guild.roles, name=settings.all_events_role_name)
        if role is None:
            raise ValueError(f"role {settings.all_events_role_name} not found")
        if action == action.ADDED:
            _logger.info(f"Adding all events role to user {user.name}")
            await user.add_roles(role)  # type: ignore
        elif action == action.REMOVED and role in user.roles:
            _logger.info(f"Removing all events role to user {user.name}")
            await user.remove_roles(role)  # type: ignore

    bot.reaction_handlers[calendar_message.id] = on_calendar_message_reaction
    _logger.info("Registered reaction handler for calendar message")


def update_rsvp(rsvp_type: MoobloomEventAttendanceType, user_id: int, event_id: int) -> None:
    with Session() as session:
        existing_rsvp: MoobloomEventRSVP | None = (
            session.query(MoobloomEventRSVP)
            .filter(MoobloomEventRSVP.event_id == event_id)
            .filter(MoobloomEventRSVP.user_id == str(user_id))
            .first()
        )
        if existing_rsvp is not None:
            existing_rsvp.attendance_type = rsvp_type
        else:
            session.add(
                MoobloomEventRSVP(user_id=user_id, event_id=event_id, attendance_type=rsvp_type)
            )

        session.commit()


def remove_rsvp(rsvp_type: MoobloomEventAttendanceType, user_id: int, event_id: int) -> None:
    with Session() as session:
        existing_rsvp: MoobloomEventRSVP | None = (
            session.query(MoobloomEventRSVP)
            .filter(MoobloomEventRSVP.event_id == event_id)
            .filter(MoobloomEventRSVP.user_id == str(user_id))
            .filter(MoobloomEventRSVP.attendance_type == rsvp_type)
            .first()
        )
        if existing_rsvp is not None:
            session.delete(existing_rsvp)
            session.commit()


def add_event_reaction_handler(bot: DiscordBot, event: MoobloomEvent) -> None:
    announcement_channel = get_announcement_channel(bot.client)

    async def on_calendar_message_reaction(
        action: ReactionAction, emoji: PartialEmoji, user: Member | User
    ) -> None:
        if not isinstance(user, Member):
            raise ValueError("bot must be used on a server")
        if emoji.name not in (
            settings.rsvp_yes_emoji,
            settings.rsvp_maybe_emoji,
            settings.rsvp_no_emoji,
        ):
            return

        rsvp_type = MoobloomEventAttendanceType.from_rsvp_react_emoji(emoji.name)
        channel = announcement_channel.guild.get_channel(int(event.channel_id))  # type: ignore
        if channel is None:
            raise ValueError(f"Channel {event.channel_id} for event {event.name} not found")
        if action == action.ADDED:
            _logger.info(f"Updating RSVP to {rsvp_type} to {event.name} for user {user.name}")
            update_rsvp(rsvp_type, user.id, event.id)  # type: ignore
            # give user access to private channel
            if rsvp_type != MoobloomEventAttendanceType.NO:
                _logger.info(f"Adding {user.name} to event channel {channel.name}")
                await channel.set_permissions(
                    user, overwrite=PermissionOverwrite(read_messages=True)
                )
            # remove reactions from other rsvp types
            message = await announcement_channel.fetch_message(int(event.announcement_message_id))  # type: ignore
            if message is None:
                raise ValueError(f"announcement message {event.announcement_message_id} not found")
            for other_rsvp_type in MoobloomEventAttendanceType:
                if other_rsvp_type == rsvp_type:
                    continue
                await message.remove_reaction(other_rsvp_type.rsvp_react_emoji, user)  # type: ignore
        elif action == action.REMOVED:
            _logger.info(f"Removing RSVP {rsvp_type} to {event.name} for user {user.name}")
            remove_rsvp(rsvp_type, user.id, event.id)  # type: ignore
            # avoid a race condition
            # if you change your RSVP from "yes" to "maybe", you don't want to be removed from the channel
            with Session() as session:
                if (
                    session.query(MoobloomEventRSVP)
                    .filter(MoobloomEventRSVP.event_id == event.id)
                    .filter(MoobloomEventRSVP.user_id == str(user.id))
                    .filter(MoobloomEventRSVP.attendance_type != MoobloomEventAttendanceType.NO)
                    .first()
                    is None
                ):
                    _logger.info(f"Removing {user.name} from event channel {channel.name}")
                    await channel.set_permissions(user, overwrite=None)

    if event.announcement_message_id is None:
        raise ValueError(f"Event {event.name} not yet announced!")
    bot.reaction_handlers[int(event.announcement_message_id)] = on_calendar_message_reaction
    _logger.info(f"Registered reaction handler for event {event.name}")


async def add_reaction_handlers(bot: DiscordBot) -> None:
    await add_calendar_reaction_handler(bot)

    with Session() as session:
        for event in session.query(MoobloomEvent).all():
            add_event_reaction_handler(bot, event)
