import logging
import re

import discord
from discord import Message
from discord.abc import Messageable, Snowflake
from discord.utils import utcnow

from moobot.agent.prompts import ChannelMessage
from moobot.constants import AGENT_CONTEXT_MAX_AGE, AGENT_CONTEXT_MESSAGE_LIMIT
from moobot.util.discord import mention

_logger = logging.getLogger(__name__)


def get_user_mention_regex(user_id: int) -> str:
    return rf"<@!?{user_id}>"


def get_bot_role_ids(message: Message, bot_user: Snowflake) -> list[int]:
    return [
        role.id
        for role in message.role_mentions
        if role.tags is not None and role.tags.bot_id == bot_user.id
    ]


def get_bot_mention_regex(message: Message, bot_user: Snowflake) -> str:
    role_patterns = [rf"<@&{role_id}>" for role_id in get_bot_role_ids(message, bot_user)]
    return f"(?:{'|'.join([get_user_mention_regex(bot_user.id), *role_patterns])})"


def is_bot_mentioned(message: Message, bot_user: Snowflake) -> bool:
    return bot_user in message.mentions or bool(get_bot_role_ids(message, bot_user))


def format_user_mentions(content: str, message: Message, bot_user: Snowflake) -> str:
    for user in message.mentions:
        if user.id != bot_user.id:
            content = re.sub(
                get_user_mention_regex(user.id),
                f"@{user.display_name} ({mention(str(user.id))})",
                content,
            )
    return content.strip()


def get_message_content(message: Message, bot_user: Snowflake) -> str:
    content = re.sub(rf"\s*{get_bot_mention_regex(message, bot_user)}\s*", " ", message.content)
    return format_user_mentions(content, message, bot_user)


def get_context_message_content(message: Message, bot_user: discord.abc.User) -> str:
    content = re.sub(
        get_bot_mention_regex(message, bot_user), f"@{bot_user.display_name}", message.content
    )
    return format_user_mentions(content, message, bot_user)


async def get_channel_context(
    channel: Messageable,
    before: Message,
    last_seen_message_id: int | None,
    bot_user: discord.abc.User,
) -> list[ChannelMessage]:
    try:
        messages = [
            message
            async for message in channel.history(limit=AGENT_CONTEXT_MESSAGE_LIMIT, before=before)
        ]
    except discord.Forbidden:
        _logger.warning(f"Missing permission to read message history in channel {before.channel}")
        return []

    oldest_created_at = utcnow() - AGENT_CONTEXT_MAX_AGE
    channel_messages = []
    for message in sorted(messages, key=lambda m: m.id):
        if last_seen_message_id is not None and message.id <= last_seen_message_id:
            continue
        if message.created_at < oldest_created_at:
            continue
        if message.author.id == bot_user.id:
            continue
        content = get_context_message_content(message, bot_user)
        if not content:
            continue
        channel_messages.append(
            ChannelMessage(
                author_name=message.author.display_name,
                author_username=message.author.name,
                author_id=message.author.id,
                created_at=message.created_at,
                content=content,
            )
        )
    return channel_messages
