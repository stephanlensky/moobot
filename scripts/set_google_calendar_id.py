from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from moobot.db.models import GoogleApiUser
from moobot.db.session import Session
from moobot.settings import get_settings
from moobot.util.google import get_calendar_service

if TYPE_CHECKING:
    from googleapiclient._apis.calendar.v3.resources import CalendarResource  # type: ignore

_logger = logging.getLogger(__name__)
settings = get_settings()


def get_moobloom_events_calendar_id(service: CalendarResource) -> str | None:
    calendars = service.calendarList().list().execute()
    for calendar in calendars["items"]:
        if calendar["summary"] == settings.google_calendar_sync_calendar_name:
            return calendar["id"]

    return None


def main() -> None:
    with Session() as session:
        users = session.query(GoogleApiUser).all()
        for user in users:
            if user.calendar_id:
                continue
            _logger.info(f"Processing user {user.user_id}")
            service = get_calendar_service(user)
            calendar_id = get_moobloom_events_calendar_id(service)
            if calendar_id:
                user.calendar_id = calendar_id
                _logger.info("Added calendar ID to user row")
            else:
                _logger.error("Failed to add calendar ID to user row")

        session.commit()
