import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord import Member, PartialEmoji
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.db.models import GoogleCalendarType
from moobot.discord.discord_bot import ReactionAction
from moobot.events import add_calendar_reaction_handler, update_calendar_message

ALL_EVENTS_EMOJI = PartialEmoji(name="allevents", id=111)
GOOGLE_CALENDAR_EMOJI = PartialEmoji(name="gcal", id=222)
BIRTHDAY_EMOJI = PartialEmoji(name="🎂")
CALENDAR_MESSAGE_ID = 99


@pytest.fixture
def calendar_message(mocker: MockerFixture) -> MagicMock:
    message = MagicMock(id=CALENDAR_MESSAGE_ID, reactions=[])
    message.add_reaction = AsyncMock()
    mocker.patch("moobot.events.get_calendar_channel")
    mocker.patch("moobot.events.get_calendar_message", AsyncMock(return_value=message))
    mocker.patch(
        "moobot.events.get_custom_emoji_by_name",
        AsyncMock(
            side_effect=lambda client, name: {
                "allevents": ALL_EVENTS_EMOJI,
                "gcal": GOOGLE_CALENDAR_EMOJI,
            }[name]
        ),
    )
    mocker.patch("moobot.events.settings.get_all_event_channels_react_emoji_name", "allevents")
    mocker.patch("moobot.events.settings.google_calendar_sync_react_emoji_name", "gcal")
    return message


@pytest.fixture
def sync(mocker: MockerFixture) -> MagicMock:
    sync = MagicMock()
    sync.enable = AsyncMock()
    sync.disable = AsyncMock()
    mocker.patch("moobot.events.enable_calendar_sync", sync.enable)
    mocker.patch("moobot.events.disable_calendar_sync", sync.disable)
    return sync


def _react(action: ReactionAction, emoji: PartialEmoji) -> Member:
    bot = MagicMock(reaction_handlers={})
    user = MagicMock(spec=Member)
    user.display_name = "Alice"

    async def react() -> None:
        await add_calendar_reaction_handler(bot)
        await bot.reaction_handlers[CALENDAR_MESSAGE_ID](action, emoji, user)

    asyncio.run(react())
    return user


@pytest.mark.usefixtures("calendar_message")
@pytest.mark.parametrize(
    ("emoji", "calendar_type"),
    [
        (GOOGLE_CALENDAR_EMOJI, GoogleCalendarType.EVENTS),
        (BIRTHDAY_EMOJI, GoogleCalendarType.BIRTHDAYS),
    ],
)
def test_calendar_reaction__added__enables_matching_sync(
    sync: MagicMock, emoji: PartialEmoji, calendar_type: GoogleCalendarType
) -> None:
    user = _react(ReactionAction.ADDED, emoji)

    sync.enable.assert_awaited_once_with(user, calendar_type)
    sync.disable.assert_not_awaited()


@pytest.mark.usefixtures("calendar_message")
@pytest.mark.parametrize(
    ("emoji", "calendar_type"),
    [
        (GOOGLE_CALENDAR_EMOJI, GoogleCalendarType.EVENTS),
        (BIRTHDAY_EMOJI, GoogleCalendarType.BIRTHDAYS),
    ],
)
def test_calendar_reaction__removed__disables_matching_sync(
    sync: MagicMock, emoji: PartialEmoji, calendar_type: GoogleCalendarType
) -> None:
    user = _react(ReactionAction.REMOVED, emoji)

    sync.disable.assert_awaited_once_with(user, calendar_type)
    sync.enable.assert_not_awaited()


@pytest.mark.usefixtures("calendar_message")
def test_calendar_reaction__other_unicode_emoji__does_nothing(sync: MagicMock) -> None:
    _react(ReactionAction.ADDED, PartialEmoji(name="🐄"))

    sync.enable.assert_not_awaited()
    sync.disable.assert_not_awaited()


def test_update_calendar_message__birthday_sync_on_same_line_and_reaction_added(
    calendar_message: MagicMock, test_db_session: sessionmaker[Session], mocker: MockerFixture
) -> None:
    mocker.patch("moobot.events.Session", test_db_session)
    mocker.patch("moobot.events.get_announcement_channel")
    mocker.patch("moobot.events.get_calendar_message", AsyncMock(return_value=None))
    calendar_channel = mocker.patch("moobot.events.get_calendar_channel").return_value
    calendar_channel.send = AsyncMock(return_value=calendar_message)

    asyncio.run(update_calendar_message(MagicMock()))

    content = calendar_channel.send.await_args.kwargs["content"]
    assert (
        f"*To enable automatic syncing of events to Google Calendar, react with"
        f" {GOOGLE_CALENDAR_EMOJI}. To sync everyone's birthdays to Google Calendar, react with"
        " 🎂.*"
    ) in content.splitlines()
    added_reactions = [call.args[0] for call in calendar_message.add_reaction.await_args_list]
    assert "🎂" in added_reactions
