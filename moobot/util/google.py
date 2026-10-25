from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING

import google_auth_oauthlib.flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from moobot.db.crud.google import create_auth_session
from moobot.db.models import (
    GoogleApiUser,
    GoogleCalendarType,
    MoobloomEvent,
    MoobloomEventAttendanceType,
)
from moobot.db.session import Session
from moobot.settings import get_settings

if TYPE_CHECKING:
    from googleapiclient._apis.calendar.v3.resources import CalendarResource  # type: ignore
    from googleapiclient._apis.calendar.v3.schemas import (  # type: ignore
        Calendar,
        Event,
        EventDateTime,
    )

_logger = logging.getLogger(__name__)
settings = get_settings()

CLIENT_CONFIG = {
    "web": {
        "client_id": settings.google_client_id,
        "project_id": settings.google_project_id,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": settings.google_client_secret,
    }
}

SCOPES = ["https://www.googleapis.com/auth/calendar.app.created"]

# a leap year, so that february 29 birthdays have a valid start date
BIRTHDAY_START_YEAR = 2000


def _get_flow(code_verifier: str | None = None) -> google_auth_oauthlib.flow.Flow:
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        CLIENT_CONFIG, SCOPES, code_verifier=code_verifier
    )
    flow.redirect_uri = f"{settings.google_redirect_uri_host}/google_oauth/auth"

    return flow


def get_google_auth_url(user_id: int, calendar_type: GoogleCalendarType) -> str:
    flow = _get_flow()
    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server apps.
        access_type="offline",
        approval_prompt="force",
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes="true",
    )
    with Session() as session:
        create_auth_session(session, state, flow.code_verifier, user_id, calendar_type)

    return authorization_url


def fetch_credentials(code: str, code_verifier: str) -> Credentials:
    flow = _get_flow(code_verifier)
    flow.fetch_token(code=code)

    return flow.credentials


def get_calendar_service(user: GoogleApiUser) -> CalendarResource:
    credentials = Credentials(
        token=user.token,
        refresh_token=user.refresh_token,
        token_uri=user.token_uri,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    service = build("calendar", "v3", credentials=credentials)

    return service


def calendar_exists(service: CalendarResource, calendar_id: str) -> bool:
    try:
        service.calendars().get(calendarId=calendar_id).execute()
    except HttpError as e:
        if e.status_code not in (403, 404):
            raise
        return False
    return True


def get_calendar_name(calendar_type: GoogleCalendarType) -> str:
    if calendar_type == GoogleCalendarType.BIRTHDAYS:
        return settings.google_calendar_sync_birthday_calendar_name
    return settings.google_calendar_sync_calendar_name


def create_calendar(service: CalendarResource, calendar_type: GoogleCalendarType) -> str:
    calendar: Calendar = {"summary": get_calendar_name(calendar_type)}
    created_calendar = service.calendars().insert(body=calendar).execute()
    return created_calendar["id"]


def _build_gcalendar_event_id(event: MoobloomEvent) -> str:
    return f"moob{event.id}"


def build_gcalendar_event(
    event: MoobloomEvent, attendance_type: MoobloomEventAttendanceType
) -> Event:
    start: EventDateTime
    if event.start_time:
        start = {"dateTime": event.start_time.isoformat(), "timeZone": settings.tz}
    else:
        start = {"date": event.start_date.isoformat()}

    end: EventDateTime
    if event.end_time:
        end = {"dateTime": event.end_time.isoformat(), "timeZone": settings.tz}
    elif event.start_time:  # no end time defined, assume end of day
        end = {
            "dateTime": event.start_time.replace(hour=23, minute=59).isoformat(),
            "timeZone": settings.tz,
        }
    else:
        # gcal end dates are exclusive, so for multi day events add 1 day to the (inclusive) stored time
        if event.start_date != event.end_date:
            end = {"date": (event.end_date + timedelta(days=1)).isoformat()}
        else:
            end = {"date": event.end_date.isoformat()}

    gcalendar_event: Event = {
        "id": _build_gcalendar_event_id(event),
        "summary": event.name,
        "start": start,
        "end": end,
        "status": {
            MoobloomEventAttendanceType.YES: "confirmed",
            MoobloomEventAttendanceType.MAYBE: "tentative",
            MoobloomEventAttendanceType.NO: "cancelled",
        }[attendance_type],
    }
    if event.location is not None:
        gcalendar_event["location"] = event.location
    if event.description is not None:
        gcalendar_event["description"] = event.description

    _logger.debug(f"Built Google Calendar event: {gcalendar_event}")
    return gcalendar_event


def get_birthday_event_id(user_id: int) -> str:
    # google event ids only allow the characters a-v and 0-9
    return f"moobb{user_id}"


def build_birthday_event(user_id: int, name: str, month: int, day: int) -> Event:
    start_date = date(BIRTHDAY_START_YEAR, month, day)
    recurrence = (
        "RRULE:FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=-1"
        if (month, day) == (2, 29)
        else "RRULE:FREQ=YEARLY"
    )
    return {
        "id": get_birthday_event_id(user_id),
        "summary": f"🎂 {name}'s birthday",
        "start": {"date": start_date.isoformat()},
        "end": {"date": (start_date + timedelta(days=1)).isoformat()},
        "recurrence": [recurrence],
        "transparency": "transparent",
        "status": "confirmed",
    }


def get_gcalendar_event(
    service: CalendarResource, calendar_id: str, gcalendar_event_id: str
) -> Event | None:
    try:
        return service.events().get(calendarId=calendar_id, eventId=gcalendar_event_id).execute()
    except HttpError as e:
        if e.status_code != 404:
            raise
        return None


def set_gcalendar_event(
    service: CalendarResource, calendar_id: str, gcalendar_event: Event
) -> None:
    gcalendar_event_id = gcalendar_event["id"]
    summary = gcalendar_event["summary"]
    existing_event = get_gcalendar_event(service, calendar_id, gcalendar_event_id)
    if existing_event is not None:
        _logger.debug(f"Updating existing Google Calendar event {summary}")
        existing_event.update(gcalendar_event)
        service.events().update(
            calendarId=calendar_id, eventId=gcalendar_event_id, body=existing_event
        ).execute()
        _logger.debug(f"Done updating existing Google Calendar event {summary}")
        return

    _logger.debug(f"Creating new Google Calendar event {summary}")
    try:
        service.events().insert(calendarId=calendar_id, body=gcalendar_event).execute()
        _logger.debug(f"Done creating new Google Calendar event {summary}")
    except HttpError as e:
        if e.status_code != 404:
            raise
        _logger.warning(f"Error creating Google Calendar event {summary}: Calendar does not exist")


def cancel_gcalendar_event(
    service: CalendarResource, calendar_id: str, gcalendar_event_id: str
) -> None:
    existing_event = get_gcalendar_event(service, calendar_id, gcalendar_event_id)
    if existing_event is None or existing_event.get("status") == "cancelled":
        return
    # deleted event ids stay reserved by google, so cancel instead of deleting
    existing_event["status"] = "cancelled"
    service.events().update(
        calendarId=calendar_id, eventId=gcalendar_event_id, body=existing_event
    ).execute()
    _logger.debug(f"Cancelled Google Calendar event {gcalendar_event_id}")
