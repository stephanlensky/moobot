from __future__ import annotations

import asyncio
import calendar
import logging
from asyncio import run_coroutine_threadsafe
from datetime import date
from threading import Thread
from typing import TYPE_CHECKING

import discord
import google
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

from moobot.constants import (
    GOOGLE_CALENDAR_SYNC_DISABLE_DM,
    GOOGLE_CALENDAR_SYNC_ENABLE_DM_TEMPLATE,
    GOOGLE_CALENDAR_SYNC_ENABLE_USER_EXISTS_DM,
    GOOGLE_CALENDAR_SYNC_SETUP_COMPLETE_DM,
    GOOGLE_CALENDAR_SYNC_TOKEN_NOT_AUTHORIZED,
)
from moobot.db.crud.google import get_api_user_by_user_id, get_api_users_by_setup_finished
from moobot.db.models import (
    GoogleApiUser,
    MoobloomEvent,
    MoobloomEventAttendanceType,
    MoobloomEventRSVP,
)
from moobot.db.session import Session
from moobot.settings import get_settings
from moobot.util.format import format_event_duration, format_single_event_for_calendar
from moobot.util.google import (
    add_or_update_event,
    create_moobloom_events_calendar,
    get_calendar_service,
    get_google_auth_url,
)

if TYPE_CHECKING:
    from discord.guild import GuildChannel

    from moobot.discord.discord_bot import DiscordBot, ReactionAction

settings = get_settings()

_logger = logging.getLogger(__name__)


async def initialize_events(bot: DiscordBot) -> None:
    _logger.info("Initializing events!")
    await send_event_announcements(bot.client)
    await create_event_channels(bot.client)
    await update_calendar_message(bot.client)
    await add_reaction_handlers(bot)
    await update_out_of_sync_events(bot.client)
    await add_event_rsvp_emojis(bot.client)


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


async def send_event_announcements(client: discord.Client) -> None:
    with Session(expire_on_commit=False) as session:
        events: list[MoobloomEvent] = (
            session.query(MoobloomEvent)
            .filter(MoobloomEvent.deleted == False)
            .filter(MoobloomEvent.announcement_message_id == None)
            .all()
        )

    for event in events:
        await send_event_announcement(client, event)


def build_event_announcement_embed(event: MoobloomEvent) -> Embed:
    event_duration = format_event_duration(
        event.start_date, event.start_time, event.end_date, event.end_time
    )

    if event.location:
        description_content = f"**{event_duration} - {event.location}**"
    else:
        description_content = f"**{event_duration}**"
    if event.description:
        description_content = f"{description_content}\n{event.description}\n"

    if event.create_channel:
        description_content = (
            f"{description_content}\n*To RSVP and gain access to the event channel, react with"
            f" {settings.rsvp_yes_emoji} (going) or {settings.rsvp_maybe_emoji} (maybe). If you are"
            f" not going, react with {settings.rsvp_no_emoji}.*"
        )
    else:
        description_content = (
            f"{description_content}\n*To RSVP, react with {settings.rsvp_yes_emoji} (going) or"
            f" {settings.rsvp_maybe_emoji} (maybe). If you are not going, react with"
            f" {settings.rsvp_no_emoji}. This event does not have a dedicated channel.*"
        )

    embed = Embed(title=event.name, url=event.url, description=description_content)
    if event.image_url:
        embed.set_image(url=event.image_url)
    if event.thumbnail_url:
        embed.set_thumbnail(url=event.image_url)

    return embed


async def send_event_announcement(client: discord.Client, event: MoobloomEvent) -> None:
    _logger.info(f"Announcing event {event.name}")

    announcement_channel = get_announcement_channel(client)

    message = await announcement_channel.send(embed=build_event_announcement_embed(event))

    with Session() as session:
        session.add(event)
        event.announcement_message_id = str(message.id)
        session.commit()


async def add_event_rsvp_emojis(client: discord.Client) -> None:
    with Session() as session:
        events: list[
            MoobloomEvent
        ] = (  # if we really care about the extra api calls we can add a state filter here
            session.query(MoobloomEvent).filter(MoobloomEvent.deleted == False).all()
        )

        await asyncio.gather(*[populate_event_emojis(client, event) for event in events])

        session.commit()


async def populate_event_emojis(
    client: discord.Client, event: MoobloomEvent
) -> None:  # taking name suggestions
    announcement_channel = get_announcement_channel(client)
    message = await announcement_channel.fetch_message(event.announcement_message_id)
    if len(message.reactions) == 0:
        await message.add_reaction(settings.rsvp_yes_emoji)
        await message.add_reaction(settings.rsvp_maybe_emoji)
        await message.add_reaction(settings.rsvp_no_emoji)
        _logger.info(f"Added rsvp emojis to announcement of event {event.name}")


async def update_out_of_sync_events(client: discord.Client) -> None:
    with Session() as session:
        events: list[MoobloomEvent] = (
            session.query(MoobloomEvent)
            .filter(MoobloomEvent.deleted == False)
            .filter(MoobloomEvent.out_of_sync == True)
            .all()
        )

        for event in events:
            _logger.info(f"Updating out-of-sync event {event.name}")
            await update_event_announcement(client, event)
            await update_event_google_calendar_events(client, event)
            event.out_of_sync = False

        session.commit()


async def update_event_announcement(client: discord.Client, event: MoobloomEvent) -> None:
    if event.announcement_message_id is None:
        raise ValueError(
            f"Cannot update announcement for unnanounced event {event.name} (id={event.id})"
        )

    announcement_channel = get_announcement_channel(client)
    message = await announcement_channel.fetch_message(int(event.announcement_message_id))

    await message.edit(embed=build_event_announcement_embed(event))


async def update_event_google_calendar_events(client: discord.Client, event: MoobloomEvent) -> None:
    for rsvp in event.rsvps:
        user = await client.fetch_user(int(rsvp.user_id))
        handle_google_calendar_sync_on_rsvp(
            user, event, MoobloomEventAttendanceType(rsvp.attendance_type)
        )


async def create_event_channels(client: discord.Client) -> None:
    with Session(expire_on_commit=False) as session:
        events: list[MoobloomEvent] = (
            session.query(MoobloomEvent)
            .filter(MoobloomEvent.deleted == False)
            .filter(MoobloomEvent.create_channel == True)
            .filter(MoobloomEvent.channel_id == None)
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
            .filter(MoobloomEvent.deleted == False)
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
    if not months_sections:
        months_sections = "No upcoming events!"

    intro_section = (
        "Welcome to the Moobloom Event calendar! A full list of upcoming events is available"
        " below.\nIn order to reduce notification spam, each event has a private channel for"
        f" discussion and planning. To gain access, RSVP in {announcement_channel.mention}."
    )
    all_events_react_emoji = get_custom_emoji_by_name(
        client, settings.get_all_event_channels_react_emoji_name
    )
    all_events_react_section = (
        "To automatically gain access to all new event channels (and accept the consequences of"
        f" receiving a ton of notifications), react with {all_events_react_emoji}."
    )

    google_calendar_sync_react_emoji = get_custom_emoji_by_name(
        client, settings.google_calendar_sync_react_emoji_name
    )
    google_calendar_sync_react_section = (
        "To enable automatic syncing of events to Google Calendar, react with"
        f" {google_calendar_sync_react_emoji}."
    )

    message_content = (
        f"{intro_section}\n\n**Moobloom Event"
        f" Calendar:**\n\n{months_sections}\n\n*{all_events_react_section}*\n\n*{google_calendar_sync_react_section}*"
    )

    calendar_message = await get_calendar_message(client, calendar_channel)
    if calendar_message is None:
        _logger.info("Calendar message not found, sending new calendar")
        calendar_message = await calendar_channel.send(content=message_content)
        await calendar_message.add_reaction(google_calendar_sync_react_emoji)
    elif message_content != calendar_message.content:
        _logger.info("Updating calendar message")
        await calendar_message.edit(content=message_content)
    else:
        _logger.info("Calendar message is up to date, doing nothing")

    await add_reaction_if_missing(calendar_message, all_events_react_emoji)
    await add_reaction_if_missing(calendar_message, google_calendar_sync_react_emoji)


async def add_reaction_if_missing(message: Message, emoji: Emoji) -> None:
    if any(r for r in message.reactions if r.emoji == emoji and r.me):
        return

    await message.add_reaction(emoji)


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
    google_calendar_sync_react_emoji = get_custom_emoji_by_name(
        bot.client, settings.google_calendar_sync_react_emoji_name
    )

    if calendar_message is None:
        raise ValueError("calendar message not yet sent")

    async def handle_all_events_react(
        action: ReactionAction, emoji: PartialEmoji, user: Member
    ) -> None:
        role = get(user.guild.roles, name=settings.all_events_role_name)
        if role is None:
            raise ValueError(f"role {settings.all_events_role_name} not found")
        if action == action.ADDED:
            _logger.info(f"Adding all events role to user {user.name}")
            await user.add_roles(role)  # type: ignore
        elif action == action.REMOVED and role in user.roles:
            _logger.info(f"Removing all events role to user {user.name}")
            await user.remove_roles(role)  # type: ignore

    async def handle_google_calendar_sync_react(
        action: ReactionAction, emoji: PartialEmoji, user: Member
    ) -> None:
        with Session() as session:
            google_api_user = get_api_user_by_user_id(session, user.id)
            if action == action.ADDED:
                _logger.info(f"Reaction for Google Calendar sync added by {user.display_name}")
                if google_api_user is None:
                    await user.send(
                        GOOGLE_CALENDAR_SYNC_ENABLE_DM_TEMPLATE.format(
                            auth_url=get_google_auth_url(user.id)
                        )
                    )
                else:
                    await user.send(GOOGLE_CALENDAR_SYNC_ENABLE_USER_EXISTS_DM)
            elif action == action.REMOVED:
                _logger.info(f"Reaction for Google Calendar sync removed by {user.display_name}")
                if google_api_user is not None:
                    session.delete(google_api_user)
                    session.commit()
                    await user.send(GOOGLE_CALENDAR_SYNC_DISABLE_DM)

    async def on_calendar_message_reaction(
        action: ReactionAction, emoji: PartialEmoji, user: Member | User
    ) -> None:
        if not isinstance(user, Member):
            raise ValueError("bot must be used on a server")
        if emoji == all_events_react_emoji:
            await handle_all_events_react(action, emoji, user)
        elif emoji == google_calendar_sync_react_emoji:
            await handle_google_calendar_sync_react(action, emoji, user)

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

    async def on_event_message_reaction(
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

        channel: GuildChannel | None = None
        if event.create_channel and event.channel_id is not None:
            channel = announcement_channel.guild.get_channel(int(event.channel_id))
            if channel is None:
                raise ValueError(f"Channel {event.channel_id} for event {event.name} not found")
        elif event.create_channel:
            _logger.warn(f"Channel for event {event.name} not yet created")

        if action == action.ADDED and user.id != bot.client.user.id:
            _logger.info(f"Updating RSVP to {rsvp_type} to {event.name} for user {user.name}")
            update_rsvp(rsvp_type, user.id, event.id)  # type: ignore
            # give user access to private channel
            if channel is not None and rsvp_type != MoobloomEventAttendanceType.NO:
                _logger.info(f"Adding {user.name} to event channel {channel.name}")
                await channel.set_permissions(
                    user, overwrite=PermissionOverwrite(read_messages=True)
                )
            # sync to gcalendar if necessary
            handle_google_calendar_sync_on_rsvp(user, event, rsvp_type)
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
                    if channel is not None:
                        _logger.info(f"Removing {user.name} from event channel {channel.name}")
                        await channel.set_permissions(user, overwrite=None)
                    # removing reaction is equivalent to RSVPing "No" for the purposes of calendar sync
                    handle_google_calendar_sync_on_rsvp(user, event, MoobloomEventAttendanceType.NO)

    if event.announcement_message_id is None:
        raise ValueError(f"Event {event.name} not yet announced!")
    bot.reaction_handlers[int(event.announcement_message_id)] = on_event_message_reaction
    _logger.info(f"Registered reaction handler for event {event.name}")


def handle_google_calendar_sync_on_rsvp(
    user: Member | User, event: MoobloomEvent, rsvp_type: MoobloomEventAttendanceType
) -> None:
    with Session() as session:
        if (google_api_user := get_api_user_by_user_id(session, user.id)) is None:
            return

    _logger.debug(
        f"Handling Google calendar sync for user {user.name}'s RSVP {rsvp_type} to {event.name}"
    )
    loop = asyncio.get_running_loop()

    def calendar_worker() -> None:
        if google_api_user is None:
            return
        calendar_service = get_calendar_service(google_api_user)
        if (calendar_id := google_api_user.calendar_id) is None:
            _logger.debug(f"Creating new Google Calendar calendar for user {user.name}")
            calendar_id = create_moobloom_events_calendar(calendar_service)
            with Session() as session:
                session.query(GoogleApiUser).filter(GoogleApiUser.id == google_api_user.id).update(
                    {GoogleApiUser.calendar_id: calendar_id}
                )
                session.commit()

        try:
            add_or_update_event(calendar_service, calendar_id, event, rsvp_type)
        except google.auth.exceptions.RefreshError:
            _logger.exception(
                f"Auth error while handling calendar sync for {user.name}. Removing user."
            )
            # user deauthed us or token expired, remove and notify
            with Session() as session:
                session.delete(google_api_user)
                session.commit()
            loop.create_task(
                user.send(GOOGLE_CALENDAR_SYNC_TOKEN_NOT_AUTHORIZED.format(name=user.display_name))
            )

    worker_thread = Thread(target=calendar_worker)
    worker_thread.run()


def complete_unfinished_google_calendar_setups(bot: DiscordBot) -> None:
    with Session() as session:
        users_with_unfinished_setup = get_api_users_by_setup_finished(session, False)

        if not users_with_unfinished_setup:
            return

        for api_user in users_with_unfinished_setup:
            discord_user_future = run_coroutine_threadsafe(
                bot.client.fetch_user(int(api_user.user_id)), bot.client.loop
            )
            discord_user = discord_user_future.result()
            _logger.info(f"Completing Google Calendar sync setup for user {discord_user.name}")

            rsvps: list[MoobloomEventRSVP] = (
                session.query(MoobloomEventRSVP)
                .join(MoobloomEventRSVP.event)
                .filter(MoobloomEventRSVP.user_id == api_user.user_id)
                .filter(MoobloomEventRSVP.attendance_type != MoobloomEventAttendanceType.NO)
                .filter(MoobloomEvent.end_date >= date.today())
                .order_by(MoobloomEvent.start_date)
                .all()
            )
            _logger.info(f"Adding Google Calendar events for {len(rsvps)} existing RSVPs")
            for rsvp in rsvps:
                event = rsvp.event
                handle_google_calendar_sync_on_rsvp(
                    discord_user, event, MoobloomEventAttendanceType(rsvp.attendance_type)
                )

            api_user.setup_finished = True
            session.commit()

            run_coroutine_threadsafe(
                discord_user.send(GOOGLE_CALENDAR_SYNC_SETUP_COMPLETE_DM), bot.client.loop
            ).result()
            _logger.info(f"Done Google Calendar sync setup for user {discord_user.name}")


async def add_reaction_handlers(bot: DiscordBot) -> None:
    await add_calendar_reaction_handler(bot)

    with Session() as session:
        for event in session.query(MoobloomEvent).filter(MoobloomEvent.deleted == False).all():
            add_event_reaction_handler(bot, event)


async def delete_event_announcement(client: discord.Client, event: MoobloomEvent) -> None:
    if not event.announcement_message_id:
        return

    announcement_channel = get_announcement_channel(client)

    message = await announcement_channel.fetch_message(int(event.announcement_message_id))
    await message.delete()
