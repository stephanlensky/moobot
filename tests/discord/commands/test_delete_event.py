import asyncio
from datetime import date
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.db.models import MoobloomEvent, MoobloomEventRSVP
from moobot.discord.commands.delete_event import delete_event, delete_event_cmd


@pytest.fixture
def session(test_db_session: sessionmaker[Session], mocker: MockerFixture) -> sessionmaker[Session]:
    mocker.patch("moobot.discord.commands.delete_event.Session", test_db_session)
    return test_db_session


def _create_event(session: sessionmaker[Session], **kwargs: object) -> int:
    with session() as db_session:
        event = MoobloomEvent(
            name="Hayride", start_date=date(2026, 10, 26), end_date=date(2026, 10, 26), **kwargs
        )
        db_session.add(event)
        db_session.commit()
        db_session.add(MoobloomEventRSVP(user_id="5", event_id=event.id, attendance_type="maybe"))
        db_session.commit()
        return event.id


def test_delete_event__existing_event__deletes_it_and_refreshes_events(
    session: sessionmaker[Session], mocker: MockerFixture
) -> None:
    delete_event_announcement = mocker.patch(
        "moobot.discord.commands.delete_event.delete_event_announcement", AsyncMock()
    )
    delete_google_calendar_event = mocker.patch(
        "moobot.discord.commands.delete_event.delete_google_calendar_event", AsyncMock()
    )
    initialize_events = mocker.patch(
        "moobot.discord.commands.delete_event.initialize_events", AsyncMock()
    )
    event_id = _create_event(session)
    bot = MagicMock()

    async def delete() -> MoobloomEvent | None:
        deleted_event = await delete_event(bot, event_id, 42)
        await asyncio.sleep(0)
        return deleted_event

    deleted_event = asyncio.run(delete())

    assert deleted_event is not None
    assert deleted_event.name == "Hayride"
    delete_event_announcement.assert_awaited_once()
    delete_google_calendar_event.assert_awaited_once_with(bot, 5, ANY)
    initialize_events.assert_awaited_once_with(bot)
    with session() as db_session:
        event = db_session.get_one(MoobloomEvent, event_id)
        assert event.deleted is True
        assert event.updated_by == "42"


@pytest.mark.parametrize("deleted", [False, True])
def test_delete_event__missing_or_deleted_event__returns_none(
    session: sessionmaker[Session], mocker: MockerFixture, deleted: bool
) -> None:
    delete_event_announcement = mocker.patch(
        "moobot.discord.commands.delete_event.delete_event_announcement", AsyncMock()
    )
    event_id = _create_event(session, deleted=True) if deleted else 99

    assert asyncio.run(delete_event(MagicMock(), event_id, 42)) is None
    delete_event_announcement.assert_not_awaited()


@pytest.mark.parametrize("confirmed", [True, False])
def test_delete_event_cmd__calls_shared_delete_only_when_confirmed(
    mocker: MockerFixture, confirmed: bool
) -> None:
    mocker.patch(
        "moobot.discord.commands.delete_event.ConfirmDelete",
        return_value=MagicMock(value=confirmed, wait=AsyncMock()),
    )
    delete_event = mocker.patch(
        "moobot.discord.commands.delete_event.delete_event",
        AsyncMock(return_value=MoobloomEvent(name="Hayride")),
    )
    bot = MagicMock()
    bot.affirm.return_value = "Sure"
    interaction = MagicMock()
    interaction.user.id = 42
    interaction.user.mention = "<@42>"
    interaction.channel.send = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()

    asyncio.run(delete_event_cmd(bot, interaction, MoobloomEvent(id=1, name="Hayride")))

    if confirmed:
        delete_event.assert_awaited_once_with(bot, 1, 42)
        interaction.followup.send.assert_awaited_once_with(
            content="Sure <@42>, I deleted event Hayride from the calendar.", ephemeral=True
        )
    else:
        delete_event.assert_not_awaited()
        interaction.followup.send.assert_awaited_once_with("Operation cancelled.", ephemeral=True)
