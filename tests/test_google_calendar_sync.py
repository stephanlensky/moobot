from datetime import date
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.db.crud.google import create_api_user, get_calendar_id, set_calendar_id
from moobot.db.models import MoobloomEvent, MoobloomEventAttendanceType
from moobot.events import handle_google_calendar_sync_on_rsvp

USER_ID = 1234


@pytest.fixture
def db_session(
    test_db_session: sessionmaker[Session], mocker: MockerFixture
) -> sessionmaker[Session]:
    mocker.patch("moobot.events.Session", test_db_session)
    with test_db_session() as session:
        create_api_user(
            session,
            user_id=USER_ID,
            token="token",
            refresh_token="refresh-token",
            token_uri="https://oauth2.googleapis.com/token",
            scopes="https://www.googleapis.com/auth/calendar.app.created",
        )
    return test_db_session


@pytest.fixture
def google(mocker: MockerFixture) -> MagicMock:
    google = MagicMock()
    mocker.patch("moobot.events.get_calendar_service", google.get_calendar_service)
    mocker.patch("moobot.events.calendar_exists", google.calendar_exists)
    mocker.patch(
        "moobot.events.create_moobloom_events_calendar", google.create_moobloom_events_calendar
    )
    mocker.patch("moobot.events.add_or_update_event", google.add_or_update_event)
    google.create_moobloom_events_calendar.return_value = "new-calendar"
    return google


def _sync() -> None:
    user = MagicMock(id=USER_ID)
    event = MoobloomEvent(
        id=1, name="event", start_date=date(2026, 1, 1), end_date=date(2026, 1, 1)
    )
    handle_google_calendar_sync_on_rsvp(MagicMock(), user, event, MoobloomEventAttendanceType.YES)


def test_sync__no_stored_calendar__creates_and_stores_calendar(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    _sync()

    google.create_moobloom_events_calendar.assert_called_once()
    assert google.add_or_update_event.call_args.args[1] == "new-calendar"
    with db_session() as session:
        assert get_calendar_id(session, USER_ID) == "new-calendar"


def test_sync__stored_calendar_exists__reuses_calendar(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    with db_session() as session:
        set_calendar_id(session, USER_ID, "old-calendar")
    google.calendar_exists.return_value = True

    _sync()

    google.create_moobloom_events_calendar.assert_not_called()
    assert google.add_or_update_event.call_args.args[1] == "old-calendar"


def test_sync__stored_calendar_deleted__replaces_calendar(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    with db_session() as session:
        set_calendar_id(session, USER_ID, "old-calendar")
    google.calendar_exists.return_value = False

    _sync()

    google.create_moobloom_events_calendar.assert_called_once()
    assert google.add_or_update_event.call_args.args[1] == "new-calendar"
    with db_session() as session:
        assert get_calendar_id(session, USER_ID) == "new-calendar"
