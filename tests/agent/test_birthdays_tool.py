import asyncio
import json
from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
from agents import FunctionTool
from agents.tool_context import ToolContext
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.agent.context import AgentContext
from moobot.agent.tools.birthdays import (
    clear_birthday,
    get_birthdays,
    get_next_birthday,
    set_birthday,
)
from moobot.db.crud import birthdays as birthday_crud

AUTHOR_ID = 42
OTHER_USER_ID = 7
BOT_USER_ID = 99


@pytest.fixture
def session(test_db_session: sessionmaker[Session], mocker: MockerFixture) -> sessionmaker[Session]:
    mocker.patch("moobot.agent.tools.birthdays.Session", test_db_session)
    mocker.patch("moobot.agent.tools.birthdays.local_today", return_value=date(2026, 10, 25))
    return test_db_session


@pytest.fixture
def sync(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "moobot.agent.tools.birthdays.handle_google_calendar_sync_on_birthday_change"
    )


def _get_context() -> AgentContext:
    bot = MagicMock()
    names = {AUTHOR_ID: "Alice", OTHER_USER_ID: "Bob", BOT_USER_ID: "Moobot"}
    guild = MagicMock()
    guild.get_member.side_effect = lambda user_id: (
        MagicMock(id=user_id, display_name=names[user_id], bot=user_id == BOT_USER_ID)
        if user_id in names
        else None
    )
    bot.client.guilds = [guild]
    return AgentContext(
        bot=bot, channel_id=1, author_id=AUTHOR_ID, author_name="Alice", message=MagicMock()
    )


def _invoke(tool: FunctionTool, context: AgentContext, **arguments: Any) -> str:
    tool_arguments = json.dumps(arguments)
    tool_context = ToolContext(
        context, tool_name=tool.name, tool_call_id="call_1", tool_arguments=tool_arguments
    )

    async def invoke() -> str:
        return str(await tool.on_invoke_tool(tool_context, tool_arguments))

    return asyncio.run(invoke())


def _get_saved_birthday(session: sessionmaker[Session], user_id: int) -> tuple[int, int] | None:
    with session() as db_session:
        birthday = birthday_crud.get_birthday(db_session, user_id)
        return (birthday.month, birthday.day) if birthday else None


def test_set_birthday__valid_date__saves_requesters_birthday_and_syncs(
    session: sessionmaker[Session], sync: MagicMock
) -> None:
    context = _get_context()

    result = _invoke(set_birthday, context, month=3, day=14)

    assert result.startswith("Saved Alice's birthday as March 14.")
    assert _get_saved_birthday(session, AUTHOR_ID) == (3, 14)
    sync.assert_called_once_with(context.bot.client, AUTHOR_ID)


def test_set_birthday__existing_birthday__replaces_it(
    session: sessionmaker[Session], sync: MagicMock
) -> None:
    with session() as db_session:
        birthday_crud.set_birthday(db_session, AUTHOR_ID, 1, 1)

    _invoke(set_birthday, _get_context(), month=2, day=29)

    assert _get_saved_birthday(session, AUTHOR_ID) == (2, 29)


@pytest.mark.parametrize(("month", "day"), [(2, 30), (13, 1), (4, 31), (0, 5)])
def test_set_birthday__invalid_date__returns_error_without_saving(
    session: sessionmaker[Session], sync: MagicMock, month: int, day: int
) -> None:
    result = _invoke(set_birthday, _get_context(), month=month, day=day)

    assert result == f"Error: {month}/{day} isn't a real date. Nothing was saved."
    assert _get_saved_birthday(session, AUTHOR_ID) is None
    sync.assert_not_called()


@pytest.mark.parametrize("user_id", ["7", "<@7>", "<@!7>"])
def test_set_birthday__other_user__saves_their_birthday_and_syncs(
    session: sessionmaker[Session], sync: MagicMock, user_id: str
) -> None:
    context = _get_context()

    result = _invoke(set_birthday, context, month=5, day=1, user_id=user_id)

    assert result.startswith("Saved Bob's birthday as May 1.")
    assert _get_saved_birthday(session, OTHER_USER_ID) == (5, 1)
    assert _get_saved_birthday(session, AUTHOR_ID) is None
    sync.assert_called_once_with(context.bot.client, OTHER_USER_ID)


@pytest.mark.parametrize("user_id", ["123", "Bob", "<@99>"])
def test_set_birthday__unknown_or_bot_user__returns_error_without_saving(
    session: sessionmaker[Session], sync: MagicMock, user_id: str
) -> None:
    result = _invoke(set_birthday, _get_context(), month=5, day=1, user_id=user_id)

    assert result.startswith(f"Error: {user_id!r} isn't a person in the server.")
    with session() as db_session:
        assert birthday_crud.get_birthdays(db_session) == []
    sync.assert_not_called()


def test_clear_birthday__other_user__removes_their_birthday(
    session: sessionmaker[Session], sync: MagicMock
) -> None:
    with session() as db_session:
        birthday_crud.set_birthday(db_session, AUTHOR_ID, 3, 14)
        birthday_crud.set_birthday(db_session, OTHER_USER_ID, 5, 1)

    result = _invoke(clear_birthday, _get_context(), user_id="<@7>")

    assert result == "Removed Bob's birthday."
    assert _get_saved_birthday(session, OTHER_USER_ID) is None
    assert _get_saved_birthday(session, AUTHOR_ID) == (3, 14)


def test_clear_birthday__saved__removes_only_requesters_birthday_and_syncs(
    session: sessionmaker[Session], sync: MagicMock
) -> None:
    with session() as db_session:
        birthday_crud.set_birthday(db_session, AUTHOR_ID, 3, 14)
        birthday_crud.set_birthday(db_session, OTHER_USER_ID, 5, 1)
    context = _get_context()

    result = _invoke(clear_birthday, context)

    assert result == "Removed Alice's birthday."
    assert _get_saved_birthday(session, AUTHOR_ID) is None
    assert _get_saved_birthday(session, OTHER_USER_ID) == (5, 1)
    sync.assert_called_once_with(context.bot.client, AUTHOR_ID)


def test_clear_birthday__not_saved__says_so_without_syncing(
    session: sessionmaker[Session], sync: MagicMock
) -> None:
    result = _invoke(clear_birthday, _get_context())

    assert result == "Alice doesn't have a saved birthday. Nothing was removed."
    sync.assert_not_called()


def test_get_birthdays__orders_by_next_birthday(session: sessionmaker[Session]) -> None:
    with session() as db_session:
        birthday_crud.set_birthday(db_session, AUTHOR_ID, 3, 14)
        birthday_crud.set_birthday(db_session, OTHER_USER_ID, 11, 1)

    result = json.loads(_invoke(get_birthdays, _get_context()))

    assert result == [
        {
            "name": "Bob",
            "user": "<@7>",
            "birthday": "November 1",
            "next_birthday": "2026-11-01",
            "days_until": 7,
        },
        {
            "name": "Alice",
            "user": "<@42>",
            "birthday": "March 14",
            "next_birthday": "2027-03-14",
            "days_until": 140,
        },
    ]


@pytest.mark.parametrize(
    ("month", "day", "today", "expected"),
    [
        (10, 25, date(2026, 10, 25), date(2026, 10, 25)),
        (10, 24, date(2026, 10, 25), date(2027, 10, 24)),
        (2, 29, date(2026, 10, 25), date(2027, 2, 28)),
        (2, 29, date(2027, 10, 25), date(2028, 2, 29)),
    ],
)
def test_get_next_birthday(month: int, day: int, today: date, expected: date) -> None:
    assert get_next_birthday(month, day, today) == expected
