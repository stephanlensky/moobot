import logging

from discord import Interaction, app_commands

from moobot.constants import AGENT_CONVERSATION_CLEARED_MESSAGE, AGENT_NO_CONVERSATION_MESSAGE
from moobot.db.crud.agent import (
    clear_active_conversation,
    get_or_create_active_conversation,
    get_turn_count,
    set_last_seen_message_id,
)
from moobot.db.models import AgentTurnStatus
from moobot.db.session import Session

_logger = logging.getLogger(__name__)

agent_group = app_commands.Group(name="agent", description="Manage your conversation with Moobot.")


async def clear_cmd(interaction: Interaction) -> None:
    if interaction.channel_id is None:
        await interaction.response.send_message(AGENT_NO_CONVERSATION_MESSAGE, ephemeral=True)
        return

    cleared_conversation_id = None
    cancelled_turn_count = 0
    with Session() as session:
        cleared_conversation = clear_active_conversation(session, interaction.channel_id)
        if cleared_conversation is not None:
            cleared_conversation_id = cleared_conversation.id
            cancelled_turn_count = get_turn_count(
                session, cleared_conversation_id, AgentTurnStatus.CANCELLED
            )
        conversation = get_or_create_active_conversation(session, interaction.channel_id)
        set_last_seen_message_id(session, conversation.id, interaction.id)
        conversation_id = conversation.id

    _logger.info(
        f"[channel {interaction.channel_id}] {interaction.user.display_name}"
        f" ({interaction.user.id}) cleared agent conversation {cleared_conversation_id},"
        f" cancelling {cancelled_turn_count} queued turns. New conversation {conversation_id}"
        f" starts its channel context at interaction {interaction.id}"
    )
    await interaction.response.send_message(AGENT_CONVERSATION_CLEARED_MESSAGE, ephemeral=True)


@agent_group.command(name="clear", description="Clear Moobot's conversation in this channel.")
async def clear(interaction: Interaction) -> None:
    _logger.info("Started agent clear command")
    await clear_cmd(interaction)
