from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from moobot.util.google import build_birthday_event, cancel_gcalendar_event, set_gcalendar_event

CALENDAR_ID = "calendar"


def _get_http_error(status: int) -> HttpError:
    return HttpError(MagicMock(status=status, reason="error"), b"")


def _get_service(existing_event: dict | None) -> MagicMock:
    service = MagicMock()
    get = service.events.return_value.get.return_value.execute
    if existing_event is None:
        get.side_effect = _get_http_error(404)
    else:
        get.return_value = existing_event
    return service


def test_build_birthday_event__regular_day__recurs_yearly_as_all_day_event() -> None:
    assert build_birthday_event(1234, "Alice", 3, 14) == {
        "id": "moobb1234",
        "summary": "🎂 Alice's birthday",
        "start": {"date": "2000-03-14"},
        "end": {"date": "2000-03-15"},
        "recurrence": ["RRULE:FREQ=YEARLY"],
        "transparency": "transparent",
        "status": "confirmed",
    }


def test_build_birthday_event__february_29__recurs_on_last_day_of_february() -> None:
    event = build_birthday_event(1234, "Alice", 2, 29)

    assert event["start"] == {"date": "2000-02-29"}
    assert event["end"] == {"date": "2000-03-01"}
    assert event["recurrence"] == ["RRULE:FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=-1"]


@pytest.mark.parametrize("status", ["confirmed", "cancelled"])
def test_set_gcalendar_event__existing_event__updates_it(status: str) -> None:
    service = _get_service({"id": "moobb1234", "status": status, "etag": "1"})
    event = build_birthday_event(1234, "Alice", 3, 14)

    set_gcalendar_event(service, CALENDAR_ID, event)

    service.events.return_value.insert.assert_not_called()
    update_kwargs = service.events.return_value.update.call_args.kwargs
    assert update_kwargs["eventId"] == "moobb1234"
    assert update_kwargs["body"] == {**event, "etag": "1"}


def test_set_gcalendar_event__no_existing_event__inserts_it() -> None:
    service = _get_service(None)
    event = build_birthday_event(1234, "Alice", 3, 14)

    set_gcalendar_event(service, CALENDAR_ID, event)

    service.events.return_value.insert.assert_called_once_with(calendarId=CALENDAR_ID, body=event)


def test_cancel_gcalendar_event__existing_event__sets_cancelled_instead_of_deleting() -> None:
    service = _get_service({"id": "moobb1234", "status": "confirmed"})

    cancel_gcalendar_event(service, CALENDAR_ID, "moobb1234")

    service.events.return_value.delete.assert_not_called()
    assert service.events.return_value.update.call_args.kwargs["body"]["status"] == "cancelled"


@pytest.mark.parametrize("existing_event", [None, {"id": "moobb1234", "status": "cancelled"}])
def test_cancel_gcalendar_event__missing_or_cancelled__does_nothing(
    existing_event: dict | None,
) -> None:
    service = _get_service(existing_event)

    cancel_gcalendar_event(service, CALENDAR_ID, "moobb1234")

    service.events.return_value.update.assert_not_called()
