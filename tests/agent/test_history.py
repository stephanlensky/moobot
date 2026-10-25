import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import discord
import pytest
from pytest_mock import MockerFixture

from moobot.agent.history import (
    get_channel_context,
    get_context_message_content,
    get_message_content,
)
from moobot.agent.prompts import ChannelMessage
from moobot.constants import AGENT_CONTEXT_MESSAGE_LIMIT

BOT_USER_ID = 999
CREATED_AT = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def _get_user(user_id: int, display_name: str) -> MagicMock:
    user = MagicMock(id=user_id, display_name=display_name)
    user.name = display_name.lower()
    return user


BOT_USER = _get_user(BOT_USER_ID, "Moobot")
ALICE = _get_user(1, "Alice")
BOB = _get_user(2, "Bob")


def _get_message(
    message_id: int,
    author: MagicMock,
    content: str,
    mentions: list[MagicMock] | None = None,
    created_at: datetime = CREATED_AT,
) -> MagicMock:
    return MagicMock(
        id=message_id,
        author=author,
        content=content,
        mentions=mentions or [],
        created_at=created_at,
    )


@pytest.fixture(autouse=True)
def now(mocker: MockerFixture) -> datetime:
    now = CREATED_AT + timedelta(hours=1)
    mocker.patch("moobot.agent.history.utcnow", return_value=now)
    return now


async def _iterate(messages: list[MagicMock]) -> AsyncIterator[MagicMock]:
    for message in messages:
        yield message


async def _raise_forbidden() -> AsyncIterator[MagicMock]:
    raise discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "Missing Access")
    yield


def _get_channel(messages: list[MagicMock]) -> MagicMock:
    channel = MagicMock()
    channel.history = MagicMock(return_value=_iterate(messages))
    return channel


def test_get_message_content__strips_bot_mention_and_formats_user_mentions() -> None:
    message = _get_message(
        1, ALICE, "<@999> ask <@!2> about   the hayride <@999>", mentions=[BOT_USER, BOB]
    )

    assert get_message_content(message, BOT_USER) == "ask @Bob (<@2>) about   the hayride"


def test_get_message_content__strips_bot_role_mention() -> None:
    bot_role = MagicMock(id=555)
    bot_role.tags.bot_id = BOT_USER_ID
    message = _get_message(1, ALICE, "<@&555> hi", mentions=[])
    message.role_mentions = [bot_role]

    assert get_message_content(message, BOT_USER) == "hi"


def test_get_context_message_content__names_bot_mention() -> None:
    message = _get_message(1, ALICE, "<@999> ask <@2> about it", mentions=[BOT_USER, BOB])

    assert get_context_message_content(message, BOT_USER) == "@Moobot ask @Bob (<@2>) about it"


def test_get_channel_context__filters_and_orders_oldest_first() -> None:
    before = _get_message(20, ALICE, "<@999> what do you think?", mentions=[BOT_USER])
    channel = _get_channel(
        [
            _get_message(15, BOB, "see you there"),
            _get_message(14, BOT_USER, "moo!"),
            _get_message(13, ALICE, ""),
            _get_message(12, ALICE, "<@999> moo?", mentions=[BOT_USER]),
            _get_message(11, ALICE, "hayride at 6?"),
            _get_message(10, BOB, "already seen"),
            _get_message(9, BOB, "also already seen"),
        ]
    )

    channel_messages = asyncio.run(get_channel_context(channel, before, 10, BOT_USER))

    assert channel_messages == [
        ChannelMessage(
            author_name="Alice",
            author_username="alice",
            author_id=1,
            created_at=CREATED_AT,
            content="hayride at 6?",
        ),
        ChannelMessage(
            author_name="Alice",
            author_username="alice",
            author_id=1,
            created_at=CREATED_AT,
            content="@Moobot moo?",
        ),
        ChannelMessage(
            author_name="Bob",
            author_username="bob",
            author_id=2,
            created_at=CREATED_AT,
            content="see you there",
        ),
    ]
    channel.history.assert_called_once_with(limit=AGENT_CONTEXT_MESSAGE_LIMIT, before=before)


def test_get_channel_context__no_last_seen__returns_all_messages() -> None:
    before = _get_message(20, ALICE, "<@999> hi", mentions=[BOT_USER])
    channel = _get_channel([_get_message(2, BOB, "second"), _get_message(1, ALICE, "first")])

    channel_messages = asyncio.run(get_channel_context(channel, before, None, BOT_USER))

    assert [m.content for m in channel_messages] == ["first", "second"]


def test_get_channel_context__old_messages__are_excluded(now: datetime) -> None:
    before = _get_message(20, ALICE, "<@999> hi", mentions=[BOT_USER])
    channel = _get_channel(
        [
            _get_message(2, BOB, "recent", created_at=now - timedelta(hours=23)),
            _get_message(1, ALICE, "old", created_at=now - timedelta(hours=25)),
        ]
    )

    channel_messages = asyncio.run(get_channel_context(channel, before, None, BOT_USER))

    assert [m.content for m in channel_messages] == ["recent"]


def test_get_channel_context__forbidden__returns_no_messages() -> None:
    before = _get_message(20, ALICE, "<@999> hi", mentions=[BOT_USER])
    channel = MagicMock()
    channel.history = MagicMock(return_value=_raise_forbidden())

    assert asyncio.run(get_channel_context(channel, before, None, BOT_USER)) == []
