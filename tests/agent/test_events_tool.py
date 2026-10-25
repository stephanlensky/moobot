from collections.abc import Generator
from datetime import date, datetime

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.agent.tools.events import get_events_data
from moobot.db.models import MoobloomEvent, MoobloomEventAttendanceType, MoobloomEventRSVP

TODAY = date(2026, 10, 25)
HAYRIDE_START = datetime(2026, 10, 26, 18, 0)  # noqa: DTZ001
HAYRIDE_END = datetime(2026, 10, 26, 20, 30)  # noqa: DTZ001


@pytest.fixture
def session(test_db_session: sessionmaker[Session], mocker: MockerFixture) -> Generator[Session]:
    mocker.patch("moobot.agent.tools.events.local_today", return_value=TODAY)
    with test_db_session() as session:
        yield session


def _create_event(session: Session, name: str, start_date: date, **kwargs: object) -> MoobloomEvent:
    event = MoobloomEvent(
        name=name,
        start_date=start_date,
        end_date=kwargs.pop("end_date", start_date),
        **kwargs,
    )
    session.add(event)
    session.commit()
    return event


def test_get_events_data__default__returns_upcoming_events_in_order(session: Session) -> None:
    _create_event(session, "Pumpkin Patch", date(2026, 10, 31))
    _create_event(session, "Hayride", date(2026, 10, 26))
    _create_event(session, "Ongoing Festival", date(2026, 10, 20), end_date=date(2026, 10, 27))
    _create_event(session, "Corn Maze", date(2026, 10, 1))
    _create_event(session, "Deleted Party", date(2026, 11, 1), deleted=True)

    names = [event["name"] for event in get_events_data(session)]

    assert names == ["Ongoing Festival", "Hayride", "Pumpkin Patch"]


def test_get_events_data__include_past__returns_past_events(session: Session) -> None:
    _create_event(session, "Hayride", date(2026, 10, 26))
    _create_event(session, "Corn Maze", date(2026, 10, 1))
    _create_event(session, "Deleted Party", date(2026, 9, 1), deleted=True)

    names = [event["name"] for event in get_events_data(session, include_past=True)]

    assert names == ["Corn Maze", "Hayride"]


def test_get_events_data__name__filters_case_insensitively(session: Session) -> None:
    _create_event(session, "Pumpkin Patch", date(2026, 10, 31))
    _create_event(session, "Pumpkin Carving", date(2026, 10, 30))
    _create_event(session, "Hayride", date(2026, 10, 26))

    names = [event["name"] for event in get_events_data(session, name="pumpkin")]

    assert names == ["Pumpkin Carving", "Pumpkin Patch"]


def test_get_events_data__returns_event_details_and_rsvp_counts(session: Session) -> None:
    event = _create_event(
        session,
        "Hayride",
        date(2026, 10, 26),
        start_time=HAYRIDE_START,
        end_time=HAYRIDE_END,
        location="Mapleview Farm",
        description="Bring a blanket",
        url="https://example.com/hayride",
        channel_id="999",
    )
    for user_id, attendance_type in [
        ("1", MoobloomEventAttendanceType.YES),
        ("2", MoobloomEventAttendanceType.YES),
        ("3", MoobloomEventAttendanceType.MAYBE),
    ]:
        session.add(
            MoobloomEventRSVP(user_id=user_id, event_id=event.id, attendance_type=attendance_type)
        )
    session.commit()

    assert get_events_data(session) == [
        {
            "id": event.id,
            "name": "Hayride",
            "when": "Mon. October 26 6:00 PM-8:30 PM",
            "start_date": "2026-10-26",
            "start_time": "18:00",
            "end_date": "2026-10-26",
            "end_time": "20:30",
            "location": "Mapleview Farm",
            "description": "Bring a blanket",
            "url": "https://example.com/hayride",
            "channel": "<#999>",
            "rsvp_counts": {"attending": 2, "maybe": 1, "no": 0},
        }
    ]


def test_get_events_data__event_without_optional_fields__returns_nulls(session: Session) -> None:
    _create_event(session, "Hayride", date(2026, 10, 26))

    [event] = get_events_data(session)

    assert event["start_time"] is None
    assert event["end_time"] is None
    assert event["location"] is None
    assert event["channel"] is None
    assert event["rsvp_counts"] == {"attending": 0, "maybe": 0, "no": 0}
