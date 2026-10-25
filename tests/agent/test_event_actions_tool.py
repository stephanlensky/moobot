import asyncio
import json
from datetime import date, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest
from agents import FunctionTool
from agents.tool_context import ToolContext
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.agent.context import AgentContext
from moobot.agent.tools import TOOLS
from moobot.agent.tools.event_actions import create_event, delete_event, update_event
from moobot.db.models import MoobloomEvent
from moobot.discord.views.agent_action import (
    CreateEventView,
    DeleteEventView,
    EventFields,
    UpdateEventView,
)
from moobot.discord.views.event_modal import EventTime

FROZEN_NOW = datetime(2026, 6, 15, 12)  # noqa: DTZ001
SEPTEMBER_21_7PM = datetime(2026, 9, 21, 19)  # noqa: DTZ001
SEPTEMBER_21_10PM = datetime(2026, 9, 21, 22)  # noqa: DTZ001
SEPTEMBER_21_TIME = EventTime(
    start_date=date(2026, 9, 21),
    start_time=SEPTEMBER_21_7PM,
    end_date=date(2026, 9, 21),
    end_time=SEPTEMBER_21_10PM,
)


@pytest.fixture
def session(test_db_session: sessionmaker[Session], mocker: MockerFixture) -> sessionmaker[Session]:
    mocker.patch("moobot.agent.tools.event_actions.Session", test_db_session)
    mocker.patch("moobot.discord.views.event_modal.local_now", return_value=FROZEN_NOW)
    return test_db_session


def _get_context() -> AgentContext:
    return AgentContext(
        bot=MagicMock(), channel_id=1, author_id=42, author_name="Alice", message=MagicMock()
    )


def _invoke(tool: FunctionTool, context: AgentContext, **arguments: Any) -> str:
    tool_arguments = json.dumps(arguments)
    tool_context = ToolContext(
        context, tool_name=tool.name, tool_call_id="call_1", tool_arguments=tool_arguments
    )

    async def invoke() -> str:
        return str(await tool.on_invoke_tool(tool_context, tool_arguments))

    return asyncio.run(invoke())


def _create_event(session: sessionmaker[Session], **kwargs: Any) -> int:
    with session() as db_session:
        event = MoobloomEvent(
            name="Hayride", start_date=date(2026, 10, 26), end_date=date(2026, 10, 26), **kwargs
        )
        db_session.add(event)
        db_session.commit()
        return event.id


def test_tools__includes_event_action_tools() -> None:
    assert [tool.name for tool in TOOLS] == [
        "get_events",
        "create_event",
        "update_event",
        "delete_event",
        "get_birthdays",
        "set_birthday",
        "clear_birthday",
        "start_calendar_sync",
        "stop_calendar_sync",
        "get_members",
    ]


def test_create_event__all_fields__queues_view_with_fields(session: sessionmaker[Session]) -> None:
    context = _get_context()

    result = _invoke(
        create_event,
        context,
        name="Hayride",
        time="9/21 7pm to 10pm",
        location="Mapleview Farm",
        channel_name="hayride",
        description="Bring a blanket",
        url="https://example.com/hayride",
        image_url="https://example.com/hayride.png",
    )

    assert result == (
        "A button that opens a pre-filled event form will be attached to your reply. Nothing is"
        " created until the user submits the form."
    )
    [view] = context.views
    assert isinstance(view, CreateEventView)
    assert view.author_id == 42
    assert view.original_message is context.message
    assert view.fields == EventFields(
        name="Hayride",
        time=SEPTEMBER_21_TIME,
        location="Mapleview Farm",
        channel_name="hayride",
        description="Bring a blanket",
        url="https://example.com/hayride",
        image_url="https://example.com/hayride.png",
    )


def test_create_event__missing_fields__lists_blank_fields(session: sessionmaker[Session]) -> None:
    context = _get_context()

    result = _invoke(create_event, context, location="Mapleview Farm")

    assert result.endswith(
        "Left blank for the user to fill in: name, time, channel name, description, url, image url."
    )
    [view] = context.views
    assert isinstance(view, CreateEventView)
    assert view.fields == EventFields(location="Mapleview Farm")


def test_create_event__invalid_time__returns_error_without_view(
    session: sessionmaker[Session],
) -> None:
    context = _get_context()

    result = _invoke(create_event, context, name="Hayride", time="2026-06-20 to 2026-06-15")

    assert result.startswith("Error: couldn't understand the time '2026-06-20 to 2026-06-15'")
    assert "start date" in result
    assert context.views == []


def test_update_event__existing_event__queues_view_with_changes(
    session: sessionmaker[Session],
) -> None:
    event_id = _create_event(session)
    context = _get_context()

    result = _invoke(update_event, context, event_id=event_id, time="9/21 7pm to 10pm")

    assert result == (
        "A button that opens the update form for Hayride, pre-filled with its current details and"
        " your changes, will be attached to your reply. Nothing changes until the user submits"
        " the form."
    )
    [view] = context.views
    assert isinstance(view, UpdateEventView)
    assert view.event_id == event_id
    assert view.original_message is context.message
    assert view.fields == EventFields(time=SEPTEMBER_21_TIME)


@pytest.mark.parametrize("deleted", [False, True])
def test_update_event__missing_or_deleted_event__returns_error_without_view(
    session: sessionmaker[Session], deleted: bool
) -> None:
    event_id = _create_event(session, deleted=True) if deleted else 99
    context = _get_context()

    result = _invoke(update_event, context, event_id=event_id, name="Hayride 2")

    assert result.startswith(f"Error: there's no event with id {event_id}.")
    assert context.views == []


def test_update_event__invalid_time__returns_error_without_view(
    session: sessionmaker[Session],
) -> None:
    event_id = _create_event(session)
    context = _get_context()

    result = _invoke(update_event, context, event_id=event_id, time="6/20/25")

    assert result.startswith("Error: couldn't understand the time '6/20/25'")
    assert context.views == []


def test_update_event__new_channel_name_for_existing_channel__returns_error(
    session: sessionmaker[Session],
) -> None:
    event_id = _create_event(session, channel_name="hayride")
    context = _get_context()

    result = _invoke(update_event, context, event_id=event_id, channel_name="hay-ride")

    assert result.startswith("Error: event Hayride already has the channel #hayride")
    assert context.views == []


def test_update_event__same_channel_name_with_pound__queues_view(
    session: sessionmaker[Session],
) -> None:
    event_id = _create_event(session, channel_name="hayride")
    context = _get_context()

    _invoke(update_event, context, event_id=event_id, channel_name="#hayride")

    assert len(context.views) == 1


def test_delete_event__existing_event__queues_view(session: sessionmaker[Session]) -> None:
    event_id = _create_event(session)
    context = _get_context()

    result = _invoke(delete_event, context, event_id=event_id)

    assert result == (
        "Delete and Cancel buttons for Hayride will be attached to your reply. Nothing is deleted"
        " until the user clicks Delete."
    )
    [view] = context.views
    assert isinstance(view, DeleteEventView)
    assert view.event_id == event_id
    assert view.author_id == 42
    assert view.original_message is context.message


@pytest.mark.parametrize("deleted", [False, True])
def test_delete_event__missing_or_deleted_event__returns_error_without_view(
    session: sessionmaker[Session], deleted: bool
) -> None:
    event_id = _create_event(session, deleted=True) if deleted else 99
    context = _get_context()

    result = _invoke(delete_event, context, event_id=event_id)

    assert result.startswith(f"Error: there's no event with id {event_id}.")
    assert context.views == []
