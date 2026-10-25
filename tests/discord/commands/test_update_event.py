import asyncio
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.db.models import MoobloomEvent
from moobot.discord.commands.update_event import (
    UpdateEventError,
    get_update_event_callback,
    update_event,
)


@pytest.fixture
def session(test_db_session: sessionmaker[Session], mocker: MockerFixture) -> sessionmaker[Session]:
    mocker.patch("moobot.discord.commands.update_event.Session", test_db_session)
    mocker.patch("moobot.discord.commands.update_event.initialize_events", AsyncMock())
    return test_db_session


def _create_event(session: sessionmaker[Session], **kwargs: Any) -> int:
    with session() as db_session:
        event = MoobloomEvent(
            name="Hayride", start_date=date(2026, 10, 26), end_date=date(2026, 10, 26), **kwargs
        )
        db_session.add(event)
        db_session.commit()
        return event.id


def _get_updated_event(**kwargs: Any) -> MoobloomEvent:
    return MoobloomEvent(
        name="Moonlit Hayride",
        create_channel=False,
        start_date=date(2026, 10, 27),
        end_date=date(2026, 10, 27),
        **kwargs,
    )


def _get_interaction() -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = 42
    interaction.user.mention = "<@42>"
    interaction.response.send_message = AsyncMock()
    return interaction


def _get_bot() -> MagicMock:
    bot = MagicMock()
    bot.affirm.return_value = "Sure"
    return bot


def test_update_event__existing_event__updates_and_returns_it(
    session: sessionmaker[Session],
) -> None:
    event_id = _create_event(session)

    result = asyncio.run(update_event(MagicMock(), event_id, _get_updated_event(), 42))

    assert isinstance(result, MoobloomEvent)
    assert result.id == event_id
    assert result.name == "Moonlit Hayride"
    assert result.start_date == date(2026, 10, 27)
    with session() as db_session:
        event = db_session.get_one(MoobloomEvent, event_id)
        assert event.name == "Moonlit Hayride"
        assert event.out_of_sync is True
        assert event.updated_by == "42"


@pytest.mark.parametrize("deleted", [False, True])
def test_update_event__missing_or_deleted_event__returns_not_found(
    session: sessionmaker[Session], deleted: bool
) -> None:
    event_id = _create_event(session, deleted=True) if deleted else 99

    result = asyncio.run(update_event(MagicMock(), event_id, _get_updated_event(), 42))

    assert result == UpdateEventError.EVENT_NOT_FOUND


def test_update_event__changed_channel_name__returns_error_without_updating(
    session: sessionmaker[Session],
) -> None:
    event_id = _create_event(session, channel_name="hayride")

    result = asyncio.run(
        update_event(MagicMock(), event_id, _get_updated_event(channel_name="hay-ride"), 42)
    )

    assert result == UpdateEventError.CHANNEL_NAME_CHANGED
    with session() as db_session:
        assert db_session.get_one(MoobloomEvent, event_id).name == "Hayride"


def test_update_event_callback__success__sends_ephemeral_confirmation(
    session: sessionmaker[Session],
) -> None:
    event_id = _create_event(session)
    interaction = _get_interaction()

    asyncio.run(get_update_event_callback(event_id)(_get_bot(), interaction, _get_updated_event()))

    interaction.response.send_message.assert_awaited_once_with(
        "Sure <@42>, I updated event Moonlit Hayride for you.", ephemeral=True
    )


@pytest.mark.parametrize(
    "channel_name,message",
    [
        (
            None,
            "Sorry <@42>, I couldn't locate the event you're updating. It may have been deleted.",
        ),
        ("hayride", "Sorry <@42>, updating event channel name is not currently supported."),
    ],
)
def test_update_event_callback__rejected__sends_ephemeral_error(
    session: sessionmaker[Session], channel_name: str | None, message: str
) -> None:
    event_id = _create_event(session, channel_name=channel_name) if channel_name else 99
    interaction = _get_interaction()

    asyncio.run(get_update_event_callback(event_id)(_get_bot(), interaction, _get_updated_event()))

    interaction.response.send_message.assert_awaited_once_with(message, ephemeral=True)
