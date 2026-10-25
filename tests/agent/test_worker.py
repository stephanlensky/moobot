import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, call

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

from moobot.agent.context import AgentContext
from moobot.agent.worker import (
    AgentWorker,
    log_run_items,
    send_reply,
    split_message,
)
from moobot.constants import (
    AGENT_EMPTY_OUTPUT_MESSAGE,
    AGENT_REPLY_ALLOWED_MENTIONS,
    AGENT_TRANSCRIPT_TURN_LIMIT,
)
from moobot.db.crud.agent import (
    clear_active_conversation,
    create_turn,
    get_or_create_active_conversation,
    set_turn_running,
)
from moobot.db.models import AgentConversation, AgentTurn, AgentTurnStatus
from tests.agent.test_transcript import _get_transcript, _get_turn_items

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


def _get_result(final_output: str | None) -> MagicMock:
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


def test_split_message__no_trailing_empty_chunk() -> None:
    assert split_message("a" * 8 + "\n\n", limit=8) == ["a" * 8]


def test_split_message__inside_code_block__closes_and_reopens_fence() -> None:
    text = "here:\n```py\n" + "\n".join(f"line{index}" for index in range(10)) + "\n```\ndone"

    chunks = split_message(text, limit=30)

    assert all(len(chunk) <= 30 for chunk in chunks)
    assert chunks[0].startswith("here:\n```py\n")
    for chunk in chunks[:-1]:
        assert chunk.endswith("\n```")
    for chunk in chunks[1:]:
        assert chunk.startswith("```py\n")
    assert all(chunk.count("```") % 2 == 0 for chunk in chunks)
    joined_lines = [
        line for chunk in chunks for line in chunk.split("\n") if not line.startswith("```")
    ]
    assert joined_lines == ["here:", *(f"line{index}" for index in range(10)), "done"]


def test_split_message__code_block_without_language__reopens_plain_fence() -> None:
    text = "```\n" + "a" * 20 + "\n" + "b" * 20 + "\n```"

    assert split_message(text, limit=30) == [
        "```\n" + "a" * 20 + "\n```",
        "```\n" + "b" * 20 + "\n```",
    ]


def test_split_message__long_line_in_code_block__hard_splits_within_limit() -> None:
    text = "```\n" + "a" * 50 + "\n```"

    chunks = split_message(text, limit=20)

    assert all(len(chunk) <= 20 for chunk in chunks)
    assert all(chunk.startswith("```\n") and chunk.endswith("\n```") for chunk in chunks)
    assert "".join(chunk.removeprefix("```\n").removesuffix("\n```") for chunk in chunks) == (
        "a" * 50
    )


def test_split_message__split_after_opening_fence__moves_fence_to_next_chunk() -> None:
    text = "intro\n```py\n" + "a" * 20

    assert split_message(text, limit=20) == [
        "intro",
        "```py\n" + "a" * 10 + "\n```",
        "```py\n" + "a" * 10,
    ]


def test_split_message__closed_code_block__splits_normally() -> None:
    text = "```\ncode\n```\n" + "b" * 10

    assert split_message(text, limit=14) == ["```\ncode\n```", "b" * 10]


def test_split_message__inline_code_fence__does_not_open_block() -> None:
    text = "use ```x``` ok\n" + "b" * 10

    assert split_message(text, limit=14) == ["use ```x``` ok", "b" * 10]


def test_send_reply__long_text__replies_then_sends_follow_ups() -> None:
    message = _get_message(1, "hi")
    text = "a" * 2000 + "b" * 10

    response_messages = asyncio.run(send_reply(message, text))

    message.reply.assert_awaited_once_with(
        "a" * 2000, allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS
    )
    message.channel.send.assert_awaited_once_with(
        "b" * 10, allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS
    )
    assert [response.id for response in response_messages] == [1001, 2001]


def test_worker__success__replies_and_completes_turn(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    message = _get_message(1, "what's up?")

    asyncio.run(_queue_turns(mocks, message))

    message.reply.assert_awaited_once_with("Moo!", allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS)
    mocks.get_transcript.assert_awaited_once_with("conversations/1.json")
    transcript, prompt, context = mocks.run_turn.await_args_list[0].args
    assert transcript == TRANSCRIPT
    assert "what's up?" in prompt
    assert context.channel_id == CHANNEL_ID
    assert context.author_id == 42
    assert context.message is message
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


@pytest.mark.parametrize("final_output", ["", "  \n", None])
def test_worker__empty_output__sends_fallback_and_completes_turn(
    test_db_session: sessionmaker[Session], mocks: Mocks, final_output: str | None
) -> None:
    mocks.run_turn.return_value = _get_result(final_output)
    message = _get_message(1, "hi")

    asyncio.run(_queue_turns(mocks, message))

    message.reply.assert_awaited_once_with(
        AGENT_EMPTY_OUTPUT_MESSAGE, allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS
    )
    mocks.set_transcript.assert_awaited_once_with("conversations/1.json", NEW_TRANSCRIPT)
    [turn] = _get_turns(test_db_session)
    assert turn.status == AgentTurnStatus.COMPLETED
    assert turn.output == AGENT_EMPTY_OUTPUT_MESSAGE


def test_worker__long_transcript__trims_model_input_and_saves_full_transcript(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    transcript = _get_transcript(AGENT_TRANSCRIPT_TURN_LIMIT + 2)
    dropped_items, kept_items = transcript[:10], transcript[10:]
    new_items = [{"role": "user", "content": "new"}, *_get_turn_items(99)[1:]]
    mocks.get_transcript.return_value = transcript
    mocks.run_turn.return_value.to_input_list.return_value = [*kept_items, *new_items]

    asyncio.run(_queue_turns(mocks, _get_message(1, "hi")))

    model_transcript = mocks.run_turn.await_args_list[0].args[0]
    assert model_transcript == kept_items
    assert model_transcript[0] == {"role": "user", "content": "question 2"}
    mocks.set_transcript.assert_awaited_once_with(
        "conversations/1.json", [*dropped_items, *kept_items, *new_items]
    )


def test_worker__short_transcript__sends_full_transcript(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    transcript = _get_transcript(AGENT_TRANSCRIPT_TURN_LIMIT)
    mocks.get_transcript.return_value = transcript

    asyncio.run(_queue_turns(mocks, _get_message(1, "hi")))

    assert mocks.run_turn.await_args_list[0].args[0] == transcript


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
        allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS,
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


def test_worker__failure_after_reply__sends_no_failure_reply(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    mocks.set_transcript.side_effect = RuntimeError("s3 is down")
    message = _get_message(1, "hi")

    asyncio.run(_queue_turns(mocks, message))

    message.reply.assert_awaited_once_with("Moo!", allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS)
    [turn] = _get_turns(test_db_session)
    assert turn.status == AgentTurnStatus.FAILED
    assert turn.error is not None
    assert "s3 is down" in turn.error


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


def test_start_queued_workers__running_turn_on_cleared_conversation__cancels_it(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    message = _get_message(1, "hi")
    mocks.messages[message.id] = message
    with test_db_session() as session:
        conversation = get_or_create_active_conversation(session, CHANNEL_ID)
        turn_id = create_turn(session, conversation.id, message.id, 42, "Alice", "hi").id
        set_turn_running(session, turn_id)
        clear_active_conversation(session, CHANNEL_ID)
        get_or_create_active_conversation(session, CHANNEL_ID)

    mocks.worker.start_queued_workers()

    [turn] = _get_turns(test_db_session)
    assert turn.status == AgentTurnStatus.CANCELLED
    assert turn.finished_at is not None
    assert CHANNEL_ID not in mocks.worker.tasks
    mocks.run_turn.assert_not_awaited()


def _get_view(label: str) -> MagicMock:
    view = MagicMock(label=label)
    view.message = None
    return view


def test_send_reply__views__attaches_first_to_last_chunk_and_sends_extras() -> None:
    message = _get_message(1, "hi")
    first_view, second_view = _get_view("Create event: Hayride"), _get_view("Delete event: Corn")

    response_messages = asyncio.run(
        send_reply(message, "a" * 2000 + "b" * 10, [first_view, second_view])
    )

    message.reply.assert_awaited_once_with(
        "a" * 2000, allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS
    )
    assert message.channel.send.await_args_list == [
        call("b" * 10, allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS, view=first_view),
        call("Delete event: Corn", allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS, view=second_view),
    ]
    assert first_view.message is response_messages[1]
    assert second_view.message is response_messages[2]


def test_send_reply__one_chunk_with_view__attaches_view_to_reply() -> None:
    message = _get_message(1, "hi")
    view = _get_view("Create event")

    [response_message] = asyncio.run(send_reply(message, "moo", [view]))

    message.reply.assert_awaited_once_with(
        "moo", allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS, view=view
    )
    assert view.message is response_message


def test_worker__tool_queues_view__attaches_it_and_logs_it(
    test_db_session: sessionmaker[Session], mocks: Mocks, caplog: pytest.LogCaptureFixture
) -> None:
    view = _get_view("Delete event: Hayride")

    async def run_turn(transcript: list, prompt: str, context: AgentContext) -> MagicMock:
        context.views.append(view)
        return _get_result("click it moo")

    mocks.run_turn.side_effect = run_turn
    message = _get_message(1, "delete the hayride")

    with caplog.at_level(logging.INFO, logger="moobot.agent.worker"):
        asyncio.run(_queue_turns(mocks, message))

    message.reply.assert_awaited_once_with(
        "click it moo", allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS, view=view
    )
    assert (
        f"[channel {CHANNEL_ID}] [turn 1] Attached views: Delete event: Hayride (message 1001)"
        in caplog.messages
    )


def test_worker__failure_after_tool_queues_view__sends_no_view(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    async def run_turn(transcript: list, prompt: str, context: AgentContext) -> MagicMock:
        context.views.append(_get_view("Create event"))
        raise RuntimeError("model is down")

    mocks.run_turn.side_effect = run_turn
    message = _get_message(1, "hi")

    asyncio.run(_queue_turns(mocks, message))

    message.reply.assert_awaited_once_with(
        "Sorry <@42>! Something went wrong while I was working on that.",
        allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS,
    )


NOTE = '[Event form update, not a message] Alice (@alice, <@42>) created the event "Hayride" (id 1)'


def _get_stored_transcripts(mocks: Mocks) -> dict[str, list]:
    transcripts: dict[str, list] = {"conversations/1.json": list(TRANSCRIPT)}

    async def get_transcript(key: str) -> list:
        return list(transcripts.get(key, []))

    async def set_transcript(key: str, items: list) -> None:
        transcripts[key] = list(items)

    mocks.get_transcript.side_effect = get_transcript
    mocks.set_transcript.side_effect = set_transcript
    return transcripts


def test_add_transcript_note__active_conversation__appends_note_without_running_model(
    test_db_session: sessionmaker[Session], mocks: Mocks, caplog: pytest.LogCaptureFixture
) -> None:
    transcripts = _get_stored_transcripts(mocks)
    with test_db_session() as session:
        get_or_create_active_conversation(session, CHANNEL_ID)

    with caplog.at_level(logging.INFO, logger="moobot.agent.worker"):
        asyncio.run(mocks.worker.add_transcript_note(CHANNEL_ID, NOTE))

    assert transcripts["conversations/1.json"] == [*TRANSCRIPT, {"role": "user", "content": NOTE}]
    mocks.run_turn.assert_not_awaited()
    assert _get_turns(test_db_session) == []
    assert f"[channel {CHANNEL_ID}] {NOTE}" in caplog.messages[-1]


def test_add_transcript_note__cleared_conversation__uses_active_conversation(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    transcripts = _get_stored_transcripts(mocks)
    with test_db_session() as session:
        get_or_create_active_conversation(session, CHANNEL_ID)
        clear_active_conversation(session, CHANNEL_ID)
        get_or_create_active_conversation(session, CHANNEL_ID)

    asyncio.run(mocks.worker.add_transcript_note(CHANNEL_ID, NOTE))

    assert transcripts["conversations/1.json"] == TRANSCRIPT
    assert transcripts["conversations/2.json"] == [{"role": "user", "content": NOTE}]


def test_add_transcript_note__no_active_conversation__does_nothing(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    with test_db_session() as session:
        get_or_create_active_conversation(session, CHANNEL_ID)
        clear_active_conversation(session, CHANNEL_ID)

    asyncio.run(mocks.worker.add_transcript_note(CHANNEL_ID, NOTE))

    mocks.get_transcript.assert_not_awaited()
    mocks.set_transcript.assert_not_awaited()


def test_add_transcript_note__storage_fails__logs_without_raising(
    test_db_session: sessionmaker[Session], mocks: Mocks, caplog: pytest.LogCaptureFixture
) -> None:
    mocks.set_transcript.side_effect = RuntimeError("s3 is down")
    with test_db_session() as session:
        get_or_create_active_conversation(session, CHANNEL_ID)

    asyncio.run(mocks.worker.add_transcript_note(CHANNEL_ID, NOTE))

    assert any("Failed to add transcript note" in message for message in caplog.messages)


def test_add_transcript_note__during_turn__waits_for_turn_and_keeps_both(
    test_db_session: sessionmaker[Session], mocks: Mocks
) -> None:
    transcripts = _get_stored_transcripts(mocks)
    turn_started = asyncio.Event()
    finish_turn = asyncio.Event()

    async def run_turn(transcript: list, prompt: str, context: AgentContext) -> MagicMock:
        turn_started.set()
        await finish_turn.wait()
        return _get_result("Moo!")

    mocks.run_turn.side_effect = run_turn
    message = _get_message(1, "hi")
    mocks.messages[message.id] = message

    async def run() -> None:
        mocks.worker.queue_turn(message)
        await turn_started.wait()
        note_task = asyncio.create_task(mocks.worker.add_transcript_note(CHANNEL_ID, NOTE))
        for _ in range(10):
            await asyncio.sleep(0)
        assert not note_task.done()
        assert transcripts["conversations/1.json"] == TRANSCRIPT
        finish_turn.set()
        await mocks.worker.tasks[CHANNEL_ID]
        await note_task

    asyncio.run(run())

    assert transcripts["conversations/1.json"] == [
        *NEW_TRANSCRIPT,
        {"role": "user", "content": NOTE},
    ]
