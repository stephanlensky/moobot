import asyncio
import json
from collections.abc import AsyncIterator, Generator
from datetime import date
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from agents import Model, ModelResponse, TResponseInputItem, Usage
from agents.items import TResponseOutputItem, TResponseStreamEvent
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.agent.agent import run_turn
from moobot.agent.context import AgentContext
from moobot.agent.model import get_client, get_model
from moobot.db.models import MoobloomEvent


class FakeModel(Model):
    def __init__(self, responses: list[list[TResponseOutputItem]]) -> None:
        self.responses = responses
        self.inputs: list[str | list[TResponseInputItem]] = []

    async def get_response(self, *args: Any, **kwargs: Any) -> ModelResponse:
        self.inputs.append(kwargs["input"])
        return ModelResponse(output=self.responses.pop(0), usage=Usage(), response_id=None)

    def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[TResponseStreamEvent]:
        raise NotImplementedError


@pytest.fixture
def set_model(mocker: MockerFixture) -> Generator[None]:
    mocker.patch("moobot.agent.model.settings.litellm_api_key", "test")
    get_client.cache_clear()
    get_model.cache_clear()
    yield
    get_client.cache_clear()
    get_model.cache_clear()


def _get_tool_call(name: str, arguments: dict[str, Any]) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        id="fc_1",
        call_id="call_1",
        name=name,
        arguments=json.dumps(arguments),
        type="function_call",
    )


def _get_message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id="msg_1",
        role="assistant",
        status="completed",
        type="message",
        content=[ResponseOutputText(text=text, type="output_text", annotations=[])],
    )


def test_run_turn__calls_get_events_and_returns_final_output(
    test_db_session: sessionmaker[Session], mocker: MockerFixture, set_model: None
) -> None:
    mocker.patch("moobot.agent.tools.events.Session", test_db_session)
    mocker.patch("moobot.agent.tools.events.local_today", return_value=date(2026, 10, 25))
    with test_db_session() as session:
        session.add(
            MoobloomEvent(
                name="Hayride", start_date=date(2026, 10, 26), end_date=date(2026, 10, 26)
            )
        )
        session.commit()

    model = FakeModel(
        [
            [_get_tool_call("get_events", {"name": "hay", "include_past": False})],
            [_get_message("The hayride is tomorrow! 🐄")],
        ]
    )
    mocker.patch("moobot.agent.model.OpenAIChatCompletionsModel", return_value=model)
    transcript: list[TResponseInputItem] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "moo!"},
    ]
    context = AgentContext(bot=MagicMock(), channel_id=1, author_id=2, author_name="Alice")

    result = asyncio.run(run_turn(transcript, "when is the hayride?", context))

    assert result.final_output == "The hayride is tomorrow! 🐄"
    new_transcript = result.to_input_list()
    assert new_transcript[:3] == [*transcript, {"role": "user", "content": "when is the hayride?"}]
    tool_output = next(
        cast(dict[str, Any], item)
        for item in new_transcript
        if item.get("type") == "function_call_output"
    )
    assert json.loads(tool_output["output"])[0]["name"] == "Hayride"
    assert len(model.inputs) == 2
