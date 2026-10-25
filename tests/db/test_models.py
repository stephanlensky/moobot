import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from moobot.db.models import AgentConversation, AgentTurn, AgentTurnStatus, MoobloomEvent
from moobot.util.time import now as local_now


def test_moobloom_event__channel_name_provided_with_pound__pound_is_removed() -> None:
    event = MoobloomEvent(name="some event", channel_name="#some-channel", start_date=local_now())
    assert event.channel_name == "some-channel"


def test_agent_conversation__two_active_in_channel__raises_integrity_error(
    test_db_session: sessionmaker[Session],
) -> None:
    with test_db_session() as session:
        session.add(AgentConversation(channel_id="1", transcript_key="a"))
        session.add(AgentConversation(channel_id="1", transcript_key="b"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_agent_conversation__cleared_and_active_in_channel__both_saved(
    test_db_session: sessionmaker[Session],
) -> None:
    with test_db_session() as session:
        session.add(AgentConversation(channel_id="1", transcript_key="a", cleared_at=local_now()))
        session.add(AgentConversation(channel_id="1", transcript_key="b", cleared_at=local_now()))
        session.add(AgentConversation(channel_id="1", transcript_key="c"))
        session.add(AgentConversation(channel_id="2", transcript_key="d"))
        session.commit()

        assert session.query(AgentConversation).count() == 4


def test_agent_turn__duplicate_message_id__raises_integrity_error(
    test_db_session: sessionmaker[Session],
) -> None:
    with test_db_session() as session:
        conversation = AgentConversation(channel_id="1", transcript_key="a")
        for _ in range(2):
            conversation.turns.append(
                AgentTurn(message_id="1", author_id="2", author_name="someone", content="hi")
            )
        session.add(conversation)
        with pytest.raises(IntegrityError):
            session.commit()


def test_agent_turn__created__defaults_to_queued_and_orders_by_id(
    test_db_session: sessionmaker[Session],
) -> None:
    with test_db_session() as session:
        conversation = AgentConversation(channel_id="1", transcript_key="a")
        for message_id in ["1", "2", "3"]:
            conversation.turns.append(
                AgentTurn(message_id=message_id, author_id="2", author_name="someone", content="")
            )
        session.add(conversation)
        session.commit()
        session.expire_all()

        turns = session.get_one(AgentConversation, conversation.id).turns
        assert [turn.message_id for turn in turns] == ["1", "2", "3"]
        assert all(turn.status == AgentTurnStatus.QUEUED for turn in turns)
        assert turns[0].conversation.id == conversation.id
