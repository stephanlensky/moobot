import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from agents import MessageOutputItem, ReasoningItem, RunItem, ToolCallItem, ToolCallOutputItem
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
)
from openai.types.responses.response_reasoning_item import Summary
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.agent.worker import (
    REPLY_ALLOWED_MENTIONS,
    AgentWorker,
    log_run_items,
    send_reply,
    split_message,
)
from moobot.db.crud.agent import create_turn, get_or_create_active_conversation, set_turn_running
from moobot.db.models import AgentConversation, AgentTurn, AgentTurnStatus

CHANNEL_ID = 1234
BOT_USER = MagicMock(id=999, display_name="Moobot")
TRANSCRIPT = [{"role": "user", "content": "earlier"}]
NEW_TRANSCRIPT = [*TRANSCRIPT, {"role": "user", "content": "new"}]


async def _iterate(messages: list[MagicMock]) -> AsyncIterator[MagicMock]:
    for message in messages:
        yield message


@dataclass
class Mocks:
    worker: AgentWorker
    channel: MagicMock
    messages: dict[int, MagicMock]
    run_turn: AsyncMock
    get_transcript: AsyncMock
    set_transcript: AsyncMock


def _get_message(message_id: int, content: str) -> MagicMock:
    message = MagicMock(
        id=message_id, content=f"<@999> {content}", mentions=[BOT_USER], created_at=None
    )
    message.channel.id = CHANNEL_ID
    message.author = MagicMock(id=42, display_name="Alice", mention="<@42>")
    message.author.name = "alice"
    message.reply = AsyncMock(side_effect=lambda *args, **kwargs: MagicMock(id=message_id + 1000))
    message.channel.send = AsyncMock(
        side_effect=lambda *args, **kwargs: MagicMock(id=message_id + 2000)
    )
    return message


def _get_result(final_output: str) -> MagicMock:
    result = MagicMock(final_output=final_output)
    result.to_input_list.return_value = NEW_TRANSCRIPT
    return result


@pytest.fixture
def mocks(test_db_session: sessionmaker[Session], mocker: MockerFixture) -> Mocks:
    mocker.patch("moobot.agent.worker.Session", test_db_session)
    messages: dict[int, MagicMock] = {}

    async def fetch_message(message_id: int) -> MagicMock:
        if message_id not in messages:
            raise discord.NotFound(MagicMock(status=404, reason="Not Found"), "Unknown Message")
        return messages[message_id]

    channel = MagicMock()
    channel.fetch_message = AsyncMock(side_effect=fetch_message)
    channel.history = MagicMock(side_effect=lambda **kwargs: _iterate([]))
    bot = MagicMock()
    bot.client.user = BOT_USER
    bot.client.get_partial_messageable.return_value = channel

    return Mocks(
        worker=AgentWorker(bot),
        channel=channel,
        messages=messages,
        run_turn=mocker.patch(
            "moobot.agent.worker.run_turn", AsyncMock(return_value=_get_result("Moo!"))
        ),
        get_transcript=mocker.patch(
            "moobot.agent.worker.get_transcript", AsyncMock(return_value=TRANSCRIPT)
        ),
        set_transcript=mocker.patch("moobot.agent.worker.set_transcript", AsyncMock()),
    )


async def _queue_turns(mocks: Mocks, *messages: MagicMock) -> None:
    for message in messages:
        mocks.messages[message.id] = message
        mocks.worker.queue_turn(message)
    await mocks.worker.tasks[CHANNEL_ID]


def _get_turns(test_db_session: sessionmaker[Session]) -> list[AgentTurn]:
    with test_db_session() as session:
        turns = session.query(AgentTurn).order_by(AgentTurn.id).all()
        session.expunge_all()
        return turns


def _get_conversation(test_db_session: sessionmaker[Session]) -> AgentConversation:
    with test_db_session() as session:
        conversation = session.query(AgentConversation).one()
        session.expunge_all()
        return conversation


def test_log_run_items__logs_every_item_with_turn_prefix(caplog: pytest.LogCaptureFixture) -> None:
    agent = MagicMock()
    tool_call = ResponseFunctionToolCall(
        call_id="call_1", name="get_events", arguments='{"name": "hay"}', type="function_call"
    )
    message = ResponseOutputMessage(
        id="msg_1",
        role="assistant",
        status="completed",
        type="message",
        content=[ResponseOutputText(text="Moo!\nHayride!", type="output_text", annotations=[])],
    )
    reasoning = ResponseReasoningItem(
        id="rs_1", type="reasoning", summary=[Summary(text="look it up", type="summary_text")]
    )
    items: list[RunItem] = [
        ReasoningItem(agent=agent, raw_item=reasoning),
        ToolCallItem(agent=agent, raw_item=tool_call),
        ToolCallOutputItem(
            agent=agent,
            raw_item={"type": "function_call_output", "call_id": "call_1", "output": "[]"},
            output='[{"name": "Hayride"}]',
        ),
        MessageOutputItem(agent=agent, raw_item=message),
    ]

    with caplog.at_level(logging.INFO, logger="moobot.agent.worker"):
        log_run_items(CHANNEL_ID, 7, items)

    assert caplog.messages == [
        "[channel 1234] [turn 7] Agent reasoning: look it up",
        '[channel 1234] [turn 7] Tool call get_events (call_1): {"name": "hay"}',
        '[channel 1234] [turn 7] Tool output (call_1): [{"name": "Hayride"}]',
        "[channel 1234] [turn 7] Agent message: Moo!\n[channel 1234] [turn 7] Hayride!",
    ]


def test_split_message__short_text__returns_one_chunk() -> None:
    assert split_message("moo") == ["moo"]


def test_split_message__long_text__splits_on_newlines_then_hard_limit() -> None:
    text = "a" * 6 + "\n" + "b" * 12

    assert split_message(text, limit=8) == ["aaaaaa", "bbbbbbbb", "bbbb"]


def test_send_reply__long_text__replies_then_sends_follow_ups() -> None:
    message = _get_message(1, "hi")
    text = "a" * 2000 + "b" * 10

    response_messages = asyncio.run(send_reply(message, text))

    message.reply.assert_awaited_once_with("a" * 2000, allowed_mentions=REPLY_ALLOWED_MENTIONS)
    message.channel.send.assert_awaited_once_with("b" * 10, allowed_mentions=REPLY_ALLOWED_MENTIONS)
    assert [response.id for response in response_messages] == [1001, 2001]


def test_worker__success__replies_and_completes_turn(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    message = _get_message(1, "what's up?")

    asyncio.run(_queue_turns(mocks, message))

    message.reply.assert_awaited_once_with("Moo!", allowed_mentions=REPLY_ALLOWED_MENTIONS)
    mocks.get_transcript.assert_awaited_once_with("conversations/1.json")
    transcript, prompt, context = mocks.run_turn.await_args_list[0].args
    assert transcript == TRANSCRIPT
    assert "what's up?" in prompt
    assert context.channel_id == CHANNEL_ID
    assert context.author_id == 42
    mocks.set_transcript.assert_awaited_once_with("conversations/1.json", NEW_TRANSCRIPT)
    mocks.channel.typing.assert_called_once()

    [turn] = _get_turns(test_db_session)
    assert turn.status == AgentTurnStatus.COMPLETED
    assert turn.content == "what's up?"
    assert turn.prompt == prompt
    assert turn.output == "Moo!"
    assert turn.response_message_id == "1001"
    assert turn.started_at is not None
    assert turn.finished_at is not None
    assert _get_conversation(test_db_session).last_seen_message_id == "1"


def test_worker__multiple_turns__runs_them_in_order(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    first_message = _get_message(1, "first")
    second_message = _get_message(2, "second")

    asyncio.run(_queue_turns(mocks, first_message, second_message))

    prompts = [call.args[1] for call in mocks.run_turn.await_args_list]
    assert len(prompts) == 2
    assert "first" in prompts[0]
    assert "second" in prompts[1]
    assert mocks.channel.history.call_args_list[1].kwargs["before"] is second_message
    assert [turn.status for turn in _get_turns(test_db_session)] == [
        AgentTurnStatus.COMPLETED,
        AgentTurnStatus.COMPLETED,
    ]
    assert _get_conversation(test_db_session).last_seen_message_id == "2"


def test_worker__failure__marks_turn_failed_and_continues(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    mocks.run_turn.side_effect = [RuntimeError("model is down"), _get_result("Moo!")]
    failed_message = _get_message(1, "first")
    message = _get_message(2, "second")

    asyncio.run(_queue_turns(mocks, failed_message, message))

    failed_message.reply.assert_awaited_once_with(
        "Sorry <@42>! Something went wrong while I was working on that.",
        allowed_mentions=REPLY_ALLOWED_MENTIONS,
    )
    mocks.set_transcript.assert_awaited_once()
    failed_turn, turn = _get_turns(test_db_session)
    assert failed_turn.status == AgentTurnStatus.FAILED
    assert failed_turn.error is not None
    assert "model is down" in failed_turn.error
    assert failed_turn.prompt is not None
    assert "first" in failed_turn.prompt
    assert failed_turn.output is None
    assert turn.status == AgentTurnStatus.COMPLETED


def test_worker__failure__saves_no_transcript(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    mocks.run_turn.side_effect = RuntimeError("model is down")

    asyncio.run(_queue_turns(mocks, _get_message(1, "hi")))

    mocks.set_transcript.assert_not_awaited()
    [turn] = _get_turns(test_db_session)
    assert turn.status == AgentTurnStatus.FAILED
    assert _get_conversation(test_db_session).last_seen_message_id is None


def test_worker__deleted_message__marks_turn_failed(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    message = _get_message(1, "hi")

    async def queue_deleted_turn() -> None:
        mocks.worker.queue_turn(message)
        await mocks.worker.tasks[CHANNEL_ID]

    asyncio.run(queue_deleted_turn())

    mocks.run_turn.assert_not_awaited()
    [turn] = _get_turns(test_db_session)
    assert turn.status == AgentTurnStatus.FAILED
    assert turn.error is not None


def test_queue_turn__duplicate_message__is_ignored(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    message = _get_message(1, "hi")

    asyncio.run(_queue_turns(mocks, message, message))

    assert len(_get_turns(test_db_session)) == 1
    mocks.run_turn.assert_awaited_once()


def test_start_queued_workers__resets_running_turns_only_once(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    message = _get_message(1, "hi")
    mocks.messages[message.id] = message
    with test_db_session() as session:
        conversation = get_or_create_active_conversation(session, CHANNEL_ID)
        turn_id = create_turn(session, conversation.id, message.id, 42, "Alice", "hi").id
        set_turn_running(session, turn_id)

    async def start_queued_workers() -> None:
        mocks.worker.start_queued_workers()
        await mocks.worker.tasks[CHANNEL_ID]

    asyncio.run(start_queued_workers())

    assert [turn.status for turn in _get_turns(test_db_session)] == [AgentTurnStatus.COMPLETED]
    mocks.run_turn.assert_awaited_once()

    with test_db_session() as session:
        set_turn_running(session, turn_id)
    mocks.worker.start_queued_workers()

    assert [turn.status for turn in _get_turns(test_db_session)] == [AgentTurnStatus.RUNNING]
