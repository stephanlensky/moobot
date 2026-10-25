import asyncio
from datetime import date
from typing import Any
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from google.auth.exceptions import RefreshError
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.calendar_sync import (
    complete_unfinished_google_calendar_setups,
    disable_calendar_sync,
    enable_calendar_sync,
    handle_google_calendar_sync_on_birthday_change,
    handle_google_calendar_sync_on_rsvp,
    sync_calendar,
)
from moobot.db.crud.birthdays import set_birthday
from moobot.db.crud.google import (
    add_calendar_sync,
    get_api_user_by_user_id,
    get_calendar_id,
    get_calendar_sync,
    set_api_user,
    set_calendar_id,
)
from moobot.db.models import (
    GoogleCalendarType,
    MoobloomEvent,
    MoobloomEventAttendanceType,
    MoobloomEventRSVP,
)

USER_ID = 1234
OTHER_USER_ID = 5678
EVENTS = GoogleCalendarType.EVENTS
BIRTHDAYS = GoogleCalendarType.BIRTHDAYS


def _add_api_user(session: Session, user_id: int = USER_ID) -> None:
    set_api_user(
        session,
        user_id=user_id,
        token="token",
        refresh_token="refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        scopes="https://www.googleapis.com/auth/calendar.app.created",
    )


@pytest.fixture
def db_session(
    test_db_session: sessionmaker[Session], mocker: MockerFixture
) -> sessionmaker[Session]:
    mocker.patch("moobot.calendar_sync.Session", test_db_session)
    return test_db_session


@pytest.fixture
def google(mocker: MockerFixture) -> MagicMock:
    google = MagicMock()
    for name in [
        "get_calendar_service",
        "calendar_exists",
        "create_calendar",
        "set_gcalendar_event",
        "cancel_gcalendar_event",
        "get_google_auth_url",
    ]:
        mocker.patch(f"moobot.calendar_sync.{name}", getattr(google, name))
    google.create_calendar.return_value = "new-calendar"
    google.get_google_auth_url.return_value = "https://auth.example"
    return google


@pytest.fixture
def run_threads(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "moobot.calendar_sync.start_thread", side_effect=lambda target, *args: target(*args)
    )


@pytest.fixture
def run_coroutine_threadsafe(mocker: MockerFixture) -> MagicMock:
    def run(coroutine: Any, loop: Any) -> MagicMock:
        future = MagicMock()
        future.result.return_value = asyncio.run(coroutine)
        return future

    return mocker.patch("moobot.calendar_sync.run_coroutine_threadsafe", side_effect=run)


def _get_client() -> MagicMock:
    client = MagicMock()
    member = MagicMock(display_name="Alice")
    guild = MagicMock()
    guild.get_member.side_effect = lambda user_id: member if user_id == USER_ID else None
    client.guilds = [guild]
    client.get_user.return_value = None
    client.fetch_user = AsyncMock(return_value=MagicMock(send=AsyncMock()))
    return client


def _get_user(user_id: int = USER_ID) -> MagicMock:
    user = MagicMock(id=user_id, display_name="Alice")
    user.name = "alice"
    user.send = AsyncMock()
    return user


def _get_event() -> MoobloomEvent:
    return MoobloomEvent(id=1, name="event", start_date=date(2026, 1, 1), end_date=date(2026, 1, 1))


def _set_events_calendar_id(google: MagicMock) -> str:
    return str(google.set_gcalendar_event.call_args.args[1])


def _sync_rsvp(client: MagicMock | None = None) -> None:
    handle_google_calendar_sync_on_rsvp(
        client or _get_client(), _get_user(), _get_event(), MoobloomEventAttendanceType.YES
    )


@pytest.fixture
def events_sync(db_session: sessionmaker[Session]) -> None:
    with db_session() as session:
        _add_api_user(session)
        add_calendar_sync(session, USER_ID, EVENTS)


@pytest.mark.usefixtures("events_sync", "run_threads")
def test_sync_rsvp__no_stored_calendar__creates_and_stores_calendar(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    _sync_rsvp()

    google.create_calendar.assert_called_once_with(ANY, EVENTS)
    assert _set_events_calendar_id(google) == "new-calendar"
    assert google.set_gcalendar_event.call_args.args[2]["id"] == "moob1"
    with db_session() as session:
        assert get_calendar_id(session, USER_ID, EVENTS) == "new-calendar"
        assert get_calendar_id(session, USER_ID, BIRTHDAYS) is None


@pytest.mark.usefixtures("events_sync", "run_threads")
def test_sync_rsvp__stored_calendar_exists__reuses_calendar(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    with db_session() as session:
        set_calendar_id(session, USER_ID, EVENTS, "old-calendar")
    google.calendar_exists.return_value = True

    _sync_rsvp()

    google.create_calendar.assert_not_called()
    assert _set_events_calendar_id(google) == "old-calendar"


@pytest.mark.usefixtures("events_sync", "run_threads")
def test_sync_rsvp__stored_calendar_deleted__replaces_calendar(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    with db_session() as session:
        set_calendar_id(session, USER_ID, EVENTS, "old-calendar")
    google.calendar_exists.return_value = False

    _sync_rsvp()

    google.create_calendar.assert_called_once()
    assert _set_events_calendar_id(google) == "new-calendar"
    with db_session() as session:
        assert get_calendar_id(session, USER_ID, EVENTS) == "new-calendar"


@pytest.mark.usefixtures("events_sync")
def test_sync_rsvp__starts_thread_instead_of_blocking(
    mocker: MockerFixture, google: MagicMock
) -> None:
    thread = mocker.patch("moobot.calendar_sync.Thread")

    _sync_rsvp()

    assert thread.call_args.kwargs["target"] is sync_calendar
    assert thread.call_args.kwargs["daemon"] is True
    thread.return_value.start.assert_called_once_with()
    thread.return_value.run.assert_not_called()
    google.set_gcalendar_event.assert_not_called()


@pytest.mark.usefixtures("run_threads")
def test_sync_rsvp__only_birthday_sync__does_nothing(
    db_session: sessionmaker[Session], google: MagicMock, run_threads: MagicMock
) -> None:
    with db_session() as session:
        _add_api_user(session)
        add_calendar_sync(session, USER_ID, BIRTHDAYS)

    _sync_rsvp()

    run_threads.assert_not_called()
    google.set_gcalendar_event.assert_not_called()


@pytest.mark.usefixtures("events_sync", "run_threads")
def test_sync_rsvp__refresh_error__removes_user_and_sends_dm(
    db_session: sessionmaker[Session], google: MagicMock, run_coroutine_threadsafe: MagicMock
) -> None:
    with db_session() as session:
        add_calendar_sync(session, USER_ID, BIRTHDAYS)
    google.set_gcalendar_event.side_effect = RefreshError()
    client = _get_client()

    _sync_rsvp(client)

    with db_session() as session:
        assert get_api_user_by_user_id(session, USER_ID) is None
        assert get_calendar_sync(session, USER_ID, EVENTS) is None
        assert get_calendar_sync(session, USER_ID, BIRTHDAYS) is None
    client.fetch_user.return_value.send.assert_awaited_once()


@pytest.fixture
def birthday_subscribers(db_session: sessionmaker[Session]) -> None:
    with db_session() as session:
        for user_id in (USER_ID, OTHER_USER_ID):
            _add_api_user(session, user_id)
            add_calendar_sync(session, user_id, BIRTHDAYS)
        add_calendar_sync(session, OTHER_USER_ID, EVENTS)


@pytest.mark.usefixtures("birthday_subscribers", "run_threads")
def test_birthday_change__set__adds_event_to_every_birthday_calendar(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    with db_session() as session:
        set_birthday(session, USER_ID, 3, 14)

    handle_google_calendar_sync_on_birthday_change(_get_client(), USER_ID)

    assert google.set_gcalendar_event.call_count == 2
    gcalendar_event = google.set_gcalendar_event.call_args.args[2]
    assert gcalendar_event["id"] == f"moobb{USER_ID}"
    assert gcalendar_event["summary"] == "🎂 Alice's birthday"
    assert gcalendar_event["start"] == {"date": "2000-03-14"}
    assert [call.args[1] for call in google.create_calendar.call_args_list] == [
        BIRTHDAYS,
        BIRTHDAYS,
    ]
    google.cancel_gcalendar_event.assert_not_called()


@pytest.mark.usefixtures("birthday_subscribers", "run_threads")
def test_birthday_change__cleared__cancels_event_in_every_birthday_calendar(
    google: MagicMock,
) -> None:
    handle_google_calendar_sync_on_birthday_change(_get_client(), USER_ID)

    assert [call.args[2] for call in google.cancel_gcalendar_event.call_args_list] == [
        f"moobb{USER_ID}",
        f"moobb{USER_ID}",
    ]
    google.set_gcalendar_event.assert_not_called()


@pytest.mark.usefixtures("run_threads")
def test_birthday_change__no_subscribers__does_nothing(
    db_session: sessionmaker[Session], google: MagicMock, run_threads: MagicMock
) -> None:
    with db_session() as session:
        set_birthday(session, USER_ID, 3, 14)

    handle_google_calendar_sync_on_birthday_change(_get_client(), USER_ID)

    run_threads.assert_not_called()


@pytest.mark.usefixtures("run_coroutine_threadsafe")
def test_complete_setups__birthdays__adds_all_birthdays_and_finishes(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    with db_session() as session:
        _add_api_user(session)
        add_calendar_sync(session, USER_ID, BIRTHDAYS)
        set_birthday(session, USER_ID, 3, 14)
        set_birthday(session, OTHER_USER_ID, 2, 29)
    client = _get_client()

    complete_unfinished_google_calendar_setups(MagicMock(client=client))

    assert [call.args[2]["id"] for call in google.set_gcalendar_event.call_args_list] == [
        f"moobb{OTHER_USER_ID}",
        f"moobb{USER_ID}",
    ]
    assert google.set_gcalendar_event.call_args_list[0].args[2]["summary"] == (
        f"🎂 User {OTHER_USER_ID}'s birthday"
    )
    with db_session() as session:
        calendar_sync = get_calendar_sync(session, USER_ID, BIRTHDAYS)
        assert calendar_sync is not None
        assert calendar_sync.setup_finished
    client.fetch_user.return_value.send.assert_awaited_once_with(
        "Google Calendar birthday sync has been set up successfully."
    )


@pytest.mark.usefixtures("run_coroutine_threadsafe")
def test_complete_setups__events__adds_upcoming_rsvps_and_finishes(
    db_session: sessionmaker[Session], google: MagicMock, mocker: MockerFixture
) -> None:
    mocker.patch("moobot.calendar_sync.local_today", return_value=date(2026, 1, 1))
    with db_session() as session:
        _add_api_user(session)
        add_calendar_sync(session, USER_ID, EVENTS)
        session.add_all(
            [
                _get_event(),
                MoobloomEvent(
                    id=2, name="past", start_date=date(2025, 1, 1), end_date=date(2025, 1, 1)
                ),
                MoobloomEventRSVP(user_id=str(USER_ID), event_id=1, attendance_type="attending"),
                MoobloomEventRSVP(user_id=str(USER_ID), event_id=2, attendance_type="attending"),
            ]
        )
        session.commit()
    client = _get_client()

    complete_unfinished_google_calendar_setups(MagicMock(client=client))

    assert [call.args[2]["id"] for call in google.set_gcalendar_event.call_args_list] == ["moob1"]
    with db_session() as session:
        calendar_sync = get_calendar_sync(session, USER_ID, EVENTS)
        assert calendar_sync is not None
        assert calendar_sync.setup_finished
    client.fetch_user.return_value.send.assert_awaited_once_with(
        "Google Calendar sync has been set up successfully."
    )


@pytest.mark.usefixtures("run_coroutine_threadsafe")
def test_complete_setups__auth_error__does_not_finish_or_send_success(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    with db_session() as session:
        _add_api_user(session)
        add_calendar_sync(session, USER_ID, BIRTHDAYS)
    google.create_calendar.side_effect = RefreshError()
    client = _get_client()

    complete_unfinished_google_calendar_setups(MagicMock(client=client))

    with db_session() as session:
        assert get_calendar_sync(session, USER_ID, BIRTHDAYS) is None
    [call] = client.fetch_user.return_value.send.await_args_list
    assert "expired or been revoked" in call.args[0]


def test_enable__no_authorization__sends_auth_link(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    user = _get_user()

    asyncio.run(enable_calendar_sync(user, BIRTHDAYS))

    google.get_google_auth_url.assert_called_once_with(USER_ID, BIRTHDAYS)
    [message] = user.send.await_args.args
    assert "Google Calendar birthday sync" in message
    assert "https://auth.example" in message
    assert "everyone's birthdays" in message
    with db_session() as session:
        assert get_calendar_sync(session, USER_ID, BIRTHDAYS) is None


@pytest.mark.usefixtures("events_sync")
def test_enable__authorized_for_other_sync__adds_sync_without_dm(
    db_session: sessionmaker[Session], google: MagicMock
) -> None:
    user = _get_user()

    asyncio.run(enable_calendar_sync(user, BIRTHDAYS))

    google.get_google_auth_url.assert_not_called()
    user.send.assert_not_awaited()
    with db_session() as session:
        calendar_sync = get_calendar_sync(session, USER_ID, BIRTHDAYS)
        assert calendar_sync is not None
        assert not calendar_sync.setup_finished


@pytest.mark.usefixtures("events_sync")
def test_enable__already_enabled__sends_already_enabled_dm(google: MagicMock) -> None:
    user = _get_user()

    asyncio.run(enable_calendar_sync(user, EVENTS))

    google.get_google_auth_url.assert_not_called()
    [message] = user.send.await_args.args
    assert message.startswith("Hm... Google Calendar sync is already enabled")


@pytest.mark.usefixtures("events_sync")
def test_disable__other_sync_remains__keeps_authorization(
    db_session: sessionmaker[Session],
) -> None:
    with db_session() as session:
        add_calendar_sync(session, USER_ID, BIRTHDAYS)
    user = _get_user()

    asyncio.run(disable_calendar_sync(user, BIRTHDAYS))

    user.send.assert_awaited_once_with(
        "Google Calendar birthday sync has been successfully disabled."
    )
    with db_session() as session:
        assert get_calendar_sync(session, USER_ID, BIRTHDAYS) is None
        assert get_calendar_sync(session, USER_ID, EVENTS) is not None
        assert get_api_user_by_user_id(session, USER_ID) is not None


@pytest.mark.usefixtures("events_sync")
def test_disable__last_sync__removes_authorization(db_session: sessionmaker[Session]) -> None:
    asyncio.run(disable_calendar_sync(_get_user(), EVENTS))

    with db_session() as session:
        assert get_api_user_by_user_id(session, USER_ID) is None


@pytest.mark.parametrize(
    ("notify_if_not_enabled", "expected_messages"),
    [(False, []), (True, ["Hm... Google Calendar birthday sync isn't enabled"])],
)
def test_disable__not_enabled__only_notifies_when_asked(
    db_session: sessionmaker[Session], notify_if_not_enabled: bool, expected_messages: list[str]
) -> None:
    user = _get_user()

    asyncio.run(disable_calendar_sync(user, BIRTHDAYS, notify_if_not_enabled))

    messages = [call.args[0] for call in user.send.await_args_list]
    assert len(messages) == len(expected_messages)
    for message, expected_message in zip(messages, expected_messages, strict=True):
        assert message.startswith(expected_message)
