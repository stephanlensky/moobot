import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from agents import FunctionTool
from agents.tool_context import ToolContext
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.agent.context import AgentContext
from moobot.agent.tools.calendar_sync import start_calendar_sync, stop_calendar_sync
from moobot.db.crud.google import add_calendar_sync
from moobot.db.models import GoogleCalendarType
from moobot.discord.views.agent_action import StartCalendarSyncView, StopCalendarSyncView

AUTHOR_ID = 42


@pytest.fixture
def session(test_db_session: sessionmaker[Session], mocker: MockerFixture) -> sessionmaker[Session]:
    mocker.patch("moobot.calendar_sync.Session", test_db_session)
    return test_db_session


def _get_context() -> AgentContext:
    return AgentContext(
        bot=MagicMock(), channel_id=1, author_id=AUTHOR_ID, author_name="Alice", message=MagicMock()
    )


def _invoke(tool: FunctionTool, context: AgentContext, **arguments: Any) -> str:
    tool_arguments = json.dumps(arguments)
    tool_context = ToolContext(
        context, tool_name=tool.name, tool_call_id="call_1", tool_arguments=tool_arguments
    )

    async def invoke() -> str:
        return str(await tool.on_invoke_tool(tool_context, tool_arguments))

    return asyncio.run(invoke())


@pytest.mark.parametrize("calendar", list(GoogleCalendarType))
def test_start_calendar_sync__not_enabled__queues_start_view(
    session: sessionmaker[Session], calendar: GoogleCalendarType
) -> None:
    context = _get_context()

    result = _invoke(start_calendar_sync, context, calendar=calendar.value)

    assert "will be attached to your reply" in result
    [view] = context.views
    assert isinstance(view, StartCalendarSyncView)
    assert view.calendar_type == calendar
    assert view.author_id == AUTHOR_ID
    assert view.original_message is context.message


def test_start_calendar_sync__already_enabled__attaches_nothing(
    session: sessionmaker[Session],
) -> None:
    with session() as db_session:
        add_calendar_sync(db_session, AUTHOR_ID, GoogleCalendarType.BIRTHDAYS)
    context = _get_context()

    result = _invoke(start_calendar_sync, context, calendar="birthdays")

    assert result.startswith("Alice already has Google Calendar birthday sync turned on.")
    assert context.views == []


def test_stop_calendar_sync__enabled__queues_stop_view(session: sessionmaker[Session]) -> None:
    with session() as db_session:
        add_calendar_sync(db_session, AUTHOR_ID, GoogleCalendarType.EVENTS)
    context = _get_context()

    result = _invoke(stop_calendar_sync, context, calendar="events")

    assert "will be attached to your reply" in result
    [view] = context.views
    assert isinstance(view, StopCalendarSyncView)
    assert view.calendar_type == GoogleCalendarType.EVENTS


def test_stop_calendar_sync__not_enabled__attaches_nothing(
    session: sessionmaker[Session],
) -> None:
    context = _get_context()

    result = _invoke(stop_calendar_sync, context, calendar="events")

    assert result == "Alice doesn't have Google Calendar sync turned on. Nothing was attached."
    assert context.views == []


def test_calendar_sync_tools__schema__only_takes_calendar() -> None:
    for tool in (start_calendar_sync, stop_calendar_sync):
        assert tool.params_json_schema["required"] == ["calendar"]
        assert set(tool.params_json_schema["properties"]) == {"calendar"}
