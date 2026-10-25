from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from moobot.db.models import AgentConversation, AgentTurn, AgentTurnStatus


def get_active_conversation(session: Session, channel_id: int) -> AgentConversation | None:
    return (
        session.query(AgentConversation)
        .filter(
            AgentConversation.channel_id == str(channel_id),
            AgentConversation.cleared_at == None,
        )
        .one_or_none()
    )


def get_or_create_active_conversation(
    session: Session, channel_id: int, commit: bool = True
) -> AgentConversation:
    conversation = get_active_conversation(session, channel_id)
    if conversation is not None:
        return conversation

    conversation = AgentConversation(channel_id=str(channel_id), transcript_key="")
    session.add(conversation)
    session.flush()
    conversation.transcript_key = f"conversations/{conversation.id}.json"
    if commit:
        session.commit()
    return conversation


def clear_active_conversation(
    session: Session, channel_id: int, commit: bool = True
) -> AgentConversation | None:
    conversation = get_active_conversation(session, channel_id)
    if conversation is None:
        return None

    conversation.cleared_at = func.now()
    session.query(AgentTurn).filter(
        AgentTurn.conversation_id == conversation.id,
        AgentTurn.status == AgentTurnStatus.QUEUED,
    ).update({AgentTurn.status: AgentTurnStatus.CANCELLED, AgentTurn.finished_at: func.now()})
    if commit:
        session.commit()
    return conversation


def set_last_seen_message_id(
    session: Session, conversation_id: int, message_id: int, commit: bool = True
) -> None:
    conversation = session.get_one(AgentConversation, conversation_id)
    conversation.last_seen_message_id = str(message_id)
    if commit:
        session.commit()


def create_turn(
    session: Session,
    conversation_id: int,
    message_id: int,
    author_id: int,
    author_name: str,
    content: str,
    commit: bool = True,
) -> AgentTurn:
    turn = AgentTurn(
        conversation_id=conversation_id,
        status=AgentTurnStatus.QUEUED,
        message_id=str(message_id),
        author_id=str(author_id),
        author_name=author_name,
        content=content,
    )
    session.add(turn)
    if commit:
        session.commit()
    return turn


def get_next_queued_turn(session: Session, conversation_id: int) -> AgentTurn | None:
    return (
        session.query(AgentTurn)
        .filter(
            AgentTurn.conversation_id == conversation_id,
            AgentTurn.status == AgentTurnStatus.QUEUED,
        )
        .order_by(AgentTurn.id)
        .first()
    )


def set_turn_running(session: Session, turn_id: int, commit: bool = True) -> None:
    turn = session.get_one(AgentTurn, turn_id)
    turn.status = AgentTurnStatus.RUNNING
    turn.started_at = func.now()
    if commit:
        session.commit()


def set_turn_completed(
    session: Session,
    turn_id: int,
    prompt: str,
    output: str,
    response_message_id: int,
    commit: bool = True,
) -> None:
    turn = session.get_one(AgentTurn, turn_id)
    turn.status = AgentTurnStatus.COMPLETED
    turn.prompt = prompt
    turn.output = output
    turn.response_message_id = str(response_message_id)
    turn.finished_at = func.now()
    if commit:
        session.commit()


def set_turn_failed(
    session: Session, turn_id: int, error: str, prompt: str | None = None, commit: bool = True
) -> None:
    turn = session.get_one(AgentTurn, turn_id)
    turn.status = AgentTurnStatus.FAILED
    turn.prompt = prompt
    turn.error = error
    turn.finished_at = func.now()
    if commit:
        session.commit()


def get_active_conversation_ids() -> Select[tuple[int]]:
    return select(AgentConversation.id).where(AgentConversation.cleared_at == None)


def reset_running_turns(session: Session, commit: bool = True) -> int:
    count = (
        session.query(AgentTurn)
        .filter(
            AgentTurn.status == AgentTurnStatus.RUNNING,
            AgentTurn.conversation_id.in_(get_active_conversation_ids()),
        )
        .update({AgentTurn.status: AgentTurnStatus.QUEUED, AgentTurn.started_at: None})
    )
    if commit:
        session.commit()
    return count


def cancel_cleared_running_turns(session: Session, commit: bool = True) -> int:
    count = (
        session.query(AgentTurn)
        .filter(
            AgentTurn.status == AgentTurnStatus.RUNNING,
            AgentTurn.conversation_id.not_in(get_active_conversation_ids()),
        )
        .update({AgentTurn.status: AgentTurnStatus.CANCELLED, AgentTurn.finished_at: func.now()})
    )
    if commit:
        session.commit()
    return count


def get_channel_ids_with_queued_turns(session: Session) -> list[int]:
    rows = (
        session.query(AgentConversation.channel_id)
        .join(AgentTurn)
        .filter(
            AgentTurn.status == AgentTurnStatus.QUEUED,
            AgentConversation.cleared_at == None,
        )
        .distinct()
        .all()
    )
    return [int(channel_id) for (channel_id,) in rows]


def is_conversation_running(session: Session, conversation_id: int) -> bool:
    return (
        session.query(AgentTurn)
        .filter(
            AgentTurn.conversation_id == conversation_id,
            AgentTurn.status == AgentTurnStatus.RUNNING,
        )
        .first()
        is not None
    )


def get_turn_count(session: Session, conversation_id: int, status: AgentTurnStatus) -> int:
    return (
        session.query(AgentTurn)
        .filter(AgentTurn.conversation_id == conversation_id, AgentTurn.status == status)
        .count()
    )
