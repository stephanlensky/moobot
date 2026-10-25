import asyncio
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.db.models import MoobloomEvent
from moobot.discord.commands.create_event import create_event, create_event_callback


@pytest.fixture
def session(test_db_session: sessionmaker[Session], mocker: MockerFixture) -> sessionmaker[Session]:
    mocker.patch("moobot.discord.commands.create_event.Session", test_db_session)
    return test_db_session


def _get_event() -> MoobloomEvent:
    return MoobloomEvent(name="Hayride", start_date=date(2026, 10, 26), end_date=date(2026, 10, 26))


def test_create_event__saves_event_and_refreshes_events(
    session: sessionmaker[Session], mocker: MockerFixture
) -> None:
    initialize_events = mocker.patch(
        "moobot.discord.commands.create_event.initialize_events", AsyncMock()
    )
    bot = MagicMock()

    async def create() -> MoobloomEvent:
        event = await create_event(bot, _get_event())
        await asyncio.sleep(0)
        return event

    event = asyncio.run(create())

    assert event.id is not None
    assert event.name == "Hayride"
    initialize_events.assert_awaited_once_with(bot)
    with session() as db_session:
        assert db_session.get_one(MoobloomEvent, event.id).name == "Hayride"


def test_create_event_callback__sends_ephemeral_confirmation(
    session: sessionmaker[Session], mocker: MockerFixture
) -> None:
    mocker.patch("moobot.discord.commands.create_event.initialize_events", AsyncMock())
    bot = MagicMock()
    bot.affirm.return_value = "Sure"
    interaction = MagicMock()
    interaction.user.mention = "<@42>"
    interaction.response.send_message = AsyncMock()

    asyncio.run(create_event_callback(bot, interaction, _get_event()))

    interaction.response.send_message.assert_awaited_once_with(
        "Sure <@42>, I added a new event Hayride to the calendar.", ephemeral=True
    )
