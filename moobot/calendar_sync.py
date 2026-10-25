from __future__ import annotations

import logging
from asyncio import run_coroutine_threadsafe
from collections.abc import Callable
from threading import Lock, Thread
from typing import TYPE_CHECKING, Any

import discord
import google.auth.exceptions
from discord import Member, User

from moobot.constants import (
    GOOGLE_CALENDAR_SYNC_ALREADY_ENABLED_DM,
    GOOGLE_CALENDAR_SYNC_DISABLE_DM,
    GOOGLE_CALENDAR_SYNC_ENABLE_DM_TEMPLATE,
    GOOGLE_CALENDAR_SYNC_NOT_ENABLED_DM,
    GOOGLE_CALENDAR_SYNC_SETUP_COMPLETE_DM,
    GOOGLE_CALENDAR_SYNC_TOKEN_NOT_AUTHORIZED,
)
from moobot.db.crud.birthdays import get_birthday, get_birthdays
from moobot.db.crud.google import (
    add_calendar_sync,
    delete_api_user,
    delete_calendar_sync,
    get_api_user_by_user_id,
    get_calendar_id,
    get_calendar_sync,
    get_calendar_syncs,
    set_calendar_id,
    set_calendar_sync_setup_finished,
)
from moobot.db.models import (
    GoogleCalendarSync,
    GoogleCalendarType,
    MoobloomEvent,
    MoobloomEventAttendanceType,
    MoobloomEventRSVP,
)
from moobot.db.session import Session
from moobot.util.google import (
    build_birthday_event,
    build_gcalendar_event,
    calendar_exists,
    cancel_gcalendar_event,
    create_calendar,
    get_birthday_event_id,
    get_calendar_service,
    get_google_auth_url,
    set_gcalendar_event,
)
from moobot.util.time import today as local_today

if TYPE_CHECKING:
    from googleapiclient._apis.calendar.v3.resources import CalendarResource  # type: ignore
    from googleapiclient._apis.calendar.v3.schemas import Event  # type: ignore

    from moobot.discord.discord_bot import DiscordBot

_logger = logging.getLogger(__name__)

CALENDAR_SYNC_LABELS = {
    GoogleCalendarType.EVENTS: "Google Calendar sync",
    GoogleCalendarType.BIRTHDAYS: "Google Calendar birthday sync",
}
CALENDAR_SYNC_DESCRIPTIONS = {
    GoogleCalendarType.EVENTS: "your RSVPs",
    GoogleCalendarType.BIRTHDAYS: "everyone's birthdays",
}

SetEvents = Callable[["CalendarResource", str], None]

_calendar_id_locks: dict[tuple[int, GoogleCalendarType], Lock] = {}
_calendar_id_locks_lock = Lock()


def get_calendar_id_lock(user_id: int, calendar_type: GoogleCalendarType) -> Lock:
    with _calendar_id_locks_lock:
        return _calendar_id_locks.setdefault((user_id, calendar_type), Lock())


def start_thread(target: Callable[..., None], *args: Any) -> None:
    Thread(target=target, args=args, daemon=True).start()


def has_calendar_sync(user_id: int, calendar_type: GoogleCalendarType) -> bool:
    with Session() as session:
        return get_calendar_sync(session, user_id, calendar_type) is not None


def get_guild_member(client: discord.Client, user_id: int) -> Member | None:
    for guild in client.guilds:
        if (member := guild.get_member(user_id)) is not None:
            return member
    return None


def get_display_name(client: discord.Client, user_id: int) -> str:
    if (member := get_guild_member(client, user_id)) is not None:
        return member.display_name
    if (user := client.get_user(user_id)) is not None:
        return user.display_name
    return f"User {user_id}"


def get_or_create_calendar_id(
    service: CalendarResource, user_id: int, calendar_type: GoogleCalendarType
) -> str:
    with get_calendar_id_lock(user_id, calendar_type), Session() as session:
        calendar_id = get_calendar_id(session, user_id, calendar_type)
        if calendar_id is None or not calendar_exists(service, calendar_id):
            _logger.debug(f"Creating new {calendar_type.value} calendar for user {user_id}")
            calendar_id = create_calendar(service, calendar_type)
            set_calendar_id(session, user_id, calendar_type, calendar_id)
        return calendar_id


async def send_token_not_authorized_dm(client: discord.Client, user_id: int) -> None:
    user = await client.fetch_user(user_id)
    await user.send(GOOGLE_CALENDAR_SYNC_TOKEN_NOT_AUTHORIZED.format(name=user.display_name))


def sync_calendar(
    client: discord.Client, user_id: int, calendar_type: GoogleCalendarType, set_events: SetEvents
) -> None:
    with Session() as session:
        api_user = get_api_user_by_user_id(session, user_id)
        if api_user is None or get_calendar_sync(session, user_id, calendar_type) is None:
            return

    calendar_service = get_calendar_service(api_user)
    try:
        calendar_id = get_or_create_calendar_id(calendar_service, user_id, calendar_type)
        set_events(calendar_service, calendar_id)
    except google.auth.exceptions.RefreshError:
        _logger.exception(f"Auth error while syncing calendar for user {user_id}. Removing user.")
        with Session() as session:
            delete_api_user(session, user_id)
        run_coroutine_threadsafe(send_token_not_authorized_dm(client, user_id), client.loop)
    except Exception:
        _logger.exception(f"Error while syncing {calendar_type.value} calendar for user {user_id}")


def set_gcalendar_events(gcalendar_events: list[Event]) -> SetEvents:
    def set_events(service: CalendarResource, calendar_id: str) -> None:
        for gcalendar_event in gcalendar_events:
            set_gcalendar_event(service, calendar_id, gcalendar_event)

    return set_events


def handle_google_calendar_sync_on_rsvp(
    client: discord.Client,
    user: Member | User,
    event: MoobloomEvent,
    rsvp_type: MoobloomEventAttendanceType,
) -> None:
    if not has_calendar_sync(user.id, GoogleCalendarType.EVENTS):
        return

    _logger.debug(
        f"Handling Google calendar sync for user {user.name}'s RSVP {rsvp_type} to {event.name}"
    )
    gcalendar_event = build_gcalendar_event(event, rsvp_type)
    start_thread(
        sync_calendar,
        client,
        user.id,
        GoogleCalendarType.EVENTS,
        set_gcalendar_events([gcalendar_event]),
    )


def get_birthday_gcalendar_event(
    client: discord.Client, user_id: int, month: int, day: int
) -> Event:
    return build_birthday_event(user_id, get_display_name(client, user_id), month, day)


def handle_google_calendar_sync_on_birthday_change(client: discord.Client, user_id: int) -> None:
    with Session() as session:
        subscriber_ids = [
            int(s.user_id) for s in get_calendar_syncs(session, GoogleCalendarType.BIRTHDAYS)
        ]
        birthday = get_birthday(session, user_id)
        month_and_day = (birthday.month, birthday.day) if birthday is not None else None
    if not subscriber_ids:
        return

    _logger.info(f"Syncing birthday change for user {user_id} to {len(subscriber_ids)} calendars")
    set_events: SetEvents
    if month_and_day is not None:
        gcalendar_event = get_birthday_gcalendar_event(client, user_id, *month_and_day)
        set_events = set_gcalendar_events([gcalendar_event])
    else:
        gcalendar_event_id = get_birthday_event_id(user_id)

        def set_events(service: CalendarResource, calendar_id: str) -> None:
            cancel_gcalendar_event(service, calendar_id, gcalendar_event_id)

    start_thread(sync_birthday_change, client, subscriber_ids, set_events)


def sync_birthday_change(
    client: discord.Client, subscriber_ids: list[int], set_events: SetEvents
) -> None:
    for subscriber_id in subscriber_ids:
        sync_calendar(client, subscriber_id, GoogleCalendarType.BIRTHDAYS, set_events)


def sync_existing_rsvps(client: discord.Client, user_id: int) -> None:
    with Session() as session:
        rsvps: list[MoobloomEventRSVP] = (
            session.query(MoobloomEventRSVP)
            .join(MoobloomEventRSVP.event)
            .filter(MoobloomEventRSVP.user_id == str(user_id))
            .filter(MoobloomEventRSVP.attendance_type != MoobloomEventAttendanceType.NO)
            .filter(MoobloomEvent.deleted == False)
            .filter(MoobloomEvent.end_date >= local_today())
            .order_by(MoobloomEvent.start_date)
            .all()
        )
        gcalendar_events = [
            build_gcalendar_event(rsvp.event, MoobloomEventAttendanceType(rsvp.attendance_type))
            for rsvp in rsvps
        ]
    _logger.info(f"Adding Google Calendar events for {len(gcalendar_events)} existing RSVPs")
    sync_calendar(
        client, user_id, GoogleCalendarType.EVENTS, set_gcalendar_events(gcalendar_events)
    )


def sync_all_birthdays(client: discord.Client, user_id: int) -> None:
    with Session() as session:
        birthdays = [(int(b.user_id), b.month, b.day) for b in get_birthdays(session)]
    gcalendar_events = [
        get_birthday_gcalendar_event(client, birthday_user_id, month, day)
        for birthday_user_id, month, day in birthdays
    ]
    _logger.info(f"Adding Google Calendar events for {len(gcalendar_events)} birthdays")
    sync_calendar(
        client, user_id, GoogleCalendarType.BIRTHDAYS, set_gcalendar_events(gcalendar_events)
    )


def complete_calendar_sync_setup(
    client: discord.Client, sync_id: int, user_id: int, calendar_type: GoogleCalendarType
) -> None:
    _logger.info(f"Completing {calendar_type.value} calendar sync setup for user {user_id}")
    if calendar_type == GoogleCalendarType.EVENTS:
        sync_existing_rsvps(client, user_id)
    else:
        sync_all_birthdays(client, user_id)

    with Session() as session:
        if session.get(GoogleCalendarSync, sync_id) is None:
            _logger.info(f"Calendar sync {sync_id} was removed during setup")
            return
        set_calendar_sync_setup_finished(session, sync_id)

    discord_user = run_coroutine_threadsafe(client.fetch_user(user_id), client.loop).result()
    run_coroutine_threadsafe(
        discord_user.send(
            GOOGLE_CALENDAR_SYNC_SETUP_COMPLETE_DM.format(label=CALENDAR_SYNC_LABELS[calendar_type])
        ),
        client.loop,
    ).result()
    _logger.info(f"Done {calendar_type.value} calendar sync setup for user {user_id}")


def complete_unfinished_google_calendar_setups(bot: DiscordBot) -> None:
    with Session() as session:
        unfinished_syncs = [
            (s.id, int(s.user_id), GoogleCalendarType(s.calendar_type))
            for s in get_calendar_syncs(session, setup_finished=False)
        ]

    for sync_id, user_id, calendar_type in unfinished_syncs:
        complete_calendar_sync_setup(bot.client, sync_id, user_id, calendar_type)


async def enable_calendar_sync(user: Member | User, calendar_type: GoogleCalendarType) -> None:
    label = CALENDAR_SYNC_LABELS[calendar_type]
    with Session() as session:
        if get_calendar_sync(session, user.id, calendar_type) is not None:
            _logger.info(f"{label} already enabled for {user.display_name}")
            await user.send(GOOGLE_CALENDAR_SYNC_ALREADY_ENABLED_DM.format(label=label))
            return
        if get_api_user_by_user_id(session, user.id) is not None:
            _logger.info(f"Enabling {label} for {user.display_name} with existing authorization")
            add_calendar_sync(session, user.id, calendar_type)
            return

    _logger.info(f"Sending {label} authorization link to {user.display_name}")
    await user.send(
        GOOGLE_CALENDAR_SYNC_ENABLE_DM_TEMPLATE.format(
            label=label,
            auth_url=get_google_auth_url(user.id, calendar_type),
            description=CALENDAR_SYNC_DESCRIPTIONS[calendar_type],
        ),
        suppress_embeds=True,
    )


async def disable_calendar_sync(
    user: Member | User, calendar_type: GoogleCalendarType, notify_if_not_enabled: bool = False
) -> None:
    label = CALENDAR_SYNC_LABELS[calendar_type]
    with Session() as session:
        disabled = delete_calendar_sync(session, user.id, calendar_type)
    if disabled:
        _logger.info(f"Disabled {label} for {user.display_name}")
        await user.send(GOOGLE_CALENDAR_SYNC_DISABLE_DM.format(label=label))
    elif notify_if_not_enabled:
        await user.send(GOOGLE_CALENDAR_SYNC_NOT_ENABLED_DM.format(label=label))
