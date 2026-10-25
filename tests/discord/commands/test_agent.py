import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.constants import AGENT_CONVERSATION_CLEARED_MESSAGE, AGENT_NO_CONVERSATION_MESSAGE
from moobot.db.crud.agent import (
    create_turn,
    get_active_conversation,
    get_or_create_active_conversation,
)
from moobot.db.models import AgentConversation, AgentTurn, AgentTurnStatus
from moobot.discord.commands.agent import agent_group, clear_cmd

CHANNEL_ID = 1234
INTERACTION_ID = 5678


@pytest.fixture
def session(test_db_session: sessionmaker[Session], mocker: MockerFixture) -> sessionmaker[Session]:
    mocker.patch("moobot.discord.commands.agent.Session", test_db_session)
    return test_db_session


def _get_interaction(channel_id: int | None = CHANNEL_ID) -> MagicMock:
    interaction = MagicMock(id=INTERACTION_ID, channel_id=channel_id)
    interaction.response.send_message = AsyncMock()
    return interaction


def test_agent_group__has_clear_command() -> None:
    assert agent_group.name == "agent"
    assert agent_group.get_command("clear") is not None


def test_clear_cmd__active_conversation__clears_it(session: sessionmaker[Session]) -> None:
    with session() as db_session:
        conversation_id = get_or_create_active_conversation(db_session, CHANNEL_ID).id
        create_turn(db_session, conversation_id, 1, 42, "Alice", "hi")
    interaction = _get_interaction()

    asyncio.run(clear_cmd(interaction))

    interaction.response.send_message.assert_awaited_once_with(
        AGENT_CONVERSATION_CLEARED_MESSAGE, ephemeral=True
    )
    with session() as db_session:
        new_conversation = get_active_conversation(db_session, CHANNEL_ID)
        assert new_conversation is not None
        assert new_conversation.id != conversation_id
        assert new_conversation.last_seen_message_id == str(INTERACTION_ID)
        assert db_session.query(AgentTurn).one().status == AgentTurnStatus.CANCELLED


def test_clear_cmd__no_conversation__starts_context_at_clear(
    session: sessionmaker[Session],
) -> None:
    interaction = _get_interaction()

    asyncio.run(clear_cmd(interaction))

    interaction.response.send_message.assert_awaited_once_with(
        AGENT_CONVERSATION_CLEARED_MESSAGE, ephemeral=True
    )
    with session() as db_session:
        conversation = db_session.query(AgentConversation).one()
        assert conversation.last_seen_message_id == str(INTERACTION_ID)


def test_clear_cmd__no_channel__says_so(session: sessionmaker[Session]) -> None:
    interaction = _get_interaction(None)

    asyncio.run(clear_cmd(interaction))

    interaction.response.send_message.assert_awaited_once_with(
        AGENT_NO_CONVERSATION_MESSAGE, ephemeral=True
    )
