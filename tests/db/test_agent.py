from collections.abc import Generator

import pytest
from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from moobot.db.crud.agent import (
    cancel_cleared_running_turns,
    clear_active_conversation,
    create_turn,
    get_active_conversation,
    get_channel_ids_with_queued_turns,
    get_next_queued_turn,
    get_or_create_active_conversation,
    get_turn_count,
    is_conversation_running,
    reset_running_turns,
    set_last_seen_message_id,
    set_turn_completed,
    set_turn_failed,
    set_turn_running,
)
from moobot.db.models import AgentConversation, AgentTurn, AgentTurnStatus

CHANNEL_ID = 1234
OTHER_CHANNEL_ID = 5678


@pytest.fixture
def session(test_db_session: sessionmaker[Session]) -> Generator[Session]:
    with test_db_session() as session:
        yield session


def _create_turn(session: Session, conversation_id: int, message_id: int) -> AgentTurn:
    return create_turn(
        session,
        conversation_id=conversation_id,
        message_id=message_id,
        author_id=42,
        author_name="someone",
        content="hello",
    )


def test_get_or_create_active_conversation__no_conversation__creates_one(session: Session) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)

    assert conversation.channel_id == str(CHANNEL_ID)
    assert conversation.transcript_key == f"conversations/{conversation.id}.json"
    assert conversation.cleared_at is None
    assert conversation.last_seen_message_id is None


def test_get_or_create_active_conversation__active_conversation__returns_it(
    session: Session,
) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)

    assert get_or_create_active_conversation(session, CHANNEL_ID).id == conversation.id
    assert session.query(AgentConversation).count() == 1


def test_get_or_create_active_conversation__cleared_conversation__creates_new_one(
    session: Session,
) -> None:
    cleared = get_or_create_active_conversation(session, CHANNEL_ID)
    clear_active_conversation(session, CHANNEL_ID)

    conversation = get_or_create_active_conversation(session, CHANNEL_ID)

    assert conversation.id != cleared.id
    assert conversation.transcript_key != cleared.transcript_key


def test_clear_active_conversation__queued_turns__cancels_only_queued_turns(
    session: Session,
) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    running = _create_turn(session, conversation.id, message_id=1)
    queued = _create_turn(session, conversation.id, message_id=2)
    set_turn_running(session, running.id)

    cleared = clear_active_conversation(session, CHANNEL_ID)

    assert cleared is not None
    assert cleared.cleared_at is not None
    assert get_active_conversation(session, CHANNEL_ID) is None
    assert session.get_one(AgentTurn, running.id).status == AgentTurnStatus.RUNNING
    assert session.get_one(AgentTurn, running.id).finished_at is None
    assert session.get_one(AgentTurn, queued.id).status == AgentTurnStatus.CANCELLED
    assert session.get_one(AgentTurn, queued.id).finished_at is not None


def test_clear_active_conversation__no_conversation__returns_none(session: Session) -> None:
    assert clear_active_conversation(session, CHANNEL_ID) is None


def test_set_last_seen_message_id__sets_message_id(session: Session) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)

    set_last_seen_message_id(session, conversation.id, 999)

    assert conversation.last_seen_message_id == "999"


def test_create_turn__creates_queued_turn(session: Session) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)

    turn = _create_turn(session, conversation.id, message_id=1)

    assert turn.status == AgentTurnStatus.QUEUED
    assert turn.message_id == "1"
    assert turn.author_id == "42"
    assert turn.created_at is not None
    assert conversation.turns == [turn]


def test_get_next_queued_turn__several_queued_turns__returns_oldest(session: Session) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    first = _create_turn(session, conversation.id, message_id=1)
    second = _create_turn(session, conversation.id, message_id=2)

    assert get_next_queued_turn(session, conversation.id) == first
    set_turn_running(session, first.id)
    assert get_next_queued_turn(session, conversation.id) == second


def test_get_next_queued_turn__no_queued_turns__returns_none(session: Session) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)

    assert get_next_queued_turn(session, conversation.id) is None


def test_set_turn_running__sets_status_and_started_at(session: Session) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    turn = _create_turn(session, conversation.id, message_id=1)

    set_turn_running(session, turn.id)

    assert turn.status == AgentTurnStatus.RUNNING
    assert turn.started_at is not None
    assert is_conversation_running(session, conversation.id)


def test_set_turn_completed__sets_result(session: Session) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    turn = _create_turn(session, conversation.id, message_id=1)
    set_turn_running(session, turn.id)

    set_turn_completed(session, turn.id, prompt="prompt", output="output", response_message_id=2)

    assert turn.status == AgentTurnStatus.COMPLETED
    assert turn.prompt == "prompt"
    assert turn.output == "output"
    assert turn.response_message_id == "2"
    assert turn.finished_at is not None
    assert not is_conversation_running(session, conversation.id)


def test_set_turn_failed__sets_error(session: Session) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    turn = _create_turn(session, conversation.id, message_id=1)
    set_turn_running(session, turn.id)

    set_turn_failed(session, turn.id, error="traceback", prompt="prompt")

    assert turn.status == AgentTurnStatus.FAILED
    assert turn.error == "traceback"
    assert turn.prompt == "prompt"
    assert turn.finished_at is not None
    assert not is_conversation_running(session, conversation.id)


def test_reset_running_turns__running_turns__sets_them_queued(session: Session) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    running = _create_turn(session, conversation.id, message_id=1)
    completed = _create_turn(session, conversation.id, message_id=2)
    set_turn_running(session, running.id)
    set_turn_running(session, completed.id)
    set_turn_completed(session, completed.id, prompt="", output="", response_message_id=3)

    assert reset_running_turns(session) == 1

    assert running.status == AgentTurnStatus.QUEUED
    assert running.started_at is None
    assert completed.status == AgentTurnStatus.COMPLETED


def test_reset_running_turns__cleared_conversation__leaves_its_running_turns(
    session: Session,
) -> None:
    cleared_conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    cleared_running = _create_turn(session, cleared_conversation.id, message_id=1)
    set_turn_running(session, cleared_running.id)
    clear_active_conversation(session, CHANNEL_ID)
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    running = _create_turn(session, conversation.id, message_id=2)
    set_turn_running(session, running.id)

    assert reset_running_turns(session) == 1

    assert running.status == AgentTurnStatus.QUEUED
    assert cleared_running.status == AgentTurnStatus.RUNNING


def test_cancel_cleared_running_turns__cancels_only_running_turns_on_cleared_conversations(
    session: Session,
) -> None:
    cleared_conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    cleared_running = _create_turn(session, cleared_conversation.id, message_id=1)
    cleared_completed = _create_turn(session, cleared_conversation.id, message_id=2)
    set_turn_running(session, cleared_running.id)
    set_turn_running(session, cleared_completed.id)
    set_turn_completed(session, cleared_completed.id, prompt="", output="", response_message_id=3)
    clear_active_conversation(session, CHANNEL_ID)
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    running = _create_turn(session, conversation.id, message_id=4)
    set_turn_running(session, running.id)

    assert cancel_cleared_running_turns(session) == 1

    assert cleared_running.status == AgentTurnStatus.CANCELLED
    assert cleared_running.finished_at is not None
    assert cleared_completed.status == AgentTurnStatus.COMPLETED
    assert running.status == AgentTurnStatus.RUNNING


def test_get_channel_ids_with_queued_turns__returns_channels_with_queued_turns(
    session: Session,
) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    other_conversation = get_or_create_active_conversation(session, OTHER_CHANNEL_ID)
    get_or_create_active_conversation(session, 9999)
    _create_turn(session, conversation.id, message_id=1)
    _create_turn(session, conversation.id, message_id=2)
    other_turn = _create_turn(session, other_conversation.id, message_id=3)
    set_turn_running(session, other_turn.id)

    assert get_channel_ids_with_queued_turns(session) == [CHANNEL_ID]


def test_get_turn_count__counts_turns_with_status(session: Session) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    other_conversation = get_or_create_active_conversation(session, OTHER_CHANNEL_ID)
    _create_turn(session, conversation.id, message_id=1)
    _create_turn(session, conversation.id, message_id=2)
    running = _create_turn(session, conversation.id, message_id=3)
    _create_turn(session, other_conversation.id, message_id=4)
    set_turn_running(session, running.id)

    assert get_turn_count(session, conversation.id, AgentTurnStatus.QUEUED) == 2
    assert get_turn_count(session, conversation.id, AgentTurnStatus.RUNNING) == 1
    assert get_turn_count(session, conversation.id, AgentTurnStatus.FAILED) == 0


def test_get_channel_ids_with_queued_turns__cleared_conversation__is_excluded(
    session: Session,
) -> None:
    conversation = get_or_create_active_conversation(session, CHANNEL_ID)
    turn = _create_turn(session, conversation.id, message_id=1)
    session.query(AgentConversation).filter(AgentConversation.id == conversation.id).update(
        {AgentConversation.cleared_at: func.now()}
    )
    session.commit()

    assert turn.status == AgentTurnStatus.QUEUED
    assert get_channel_ids_with_queued_turns(session) == []
