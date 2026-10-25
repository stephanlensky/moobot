from dataclasses import dataclass
from datetime import datetime

from moobot.settings import get_settings
from moobot.util.discord import mention
from moobot.util.time import local_tz
from moobot.util.time import now as local_now

settings = get_settings()

DATETIME_FORMAT = "%a. %B %-d, %Y %-I:%M %p"

INSTRUCTIONS_TEMPLATE = """\
You are Moobot, a friendly cow-themed bot for the Moobloom Discord server. You help members keep \
track of the server's events.

Your replies are posted as Discord messages, so keep them concise and conversational, and format \
them with Discord markdown. Don't use headings or tables unless they really help. A little cow \
flavor is welcome, but don't overdo it.

The current date and time is {now} ({tz}). Use it to work out what "today", "this weekend", \
"next week" and similar phrases mean, and present times in this timezone.

Always use your tools to look up anything about events, such as what's coming up, when or \
where an event is, or how many people have RSVPed. Never guess or make up event details. If a \
tool doesn't return what you need, say so.

Each user message starts with any earlier messages from the channel that you haven't seen yet, \
for context, followed by the message you're replying to and who sent it. Reply only to that last \
message, using the earlier ones as context. To mention a user, write <@user_id>."""


@dataclass
class ChannelMessage:
    author_name: str
    created_at: datetime
    content: str


def format_datetime(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(local_tz())
    return value.strftime(DATETIME_FORMAT)


def get_instructions() -> str:
    return INSTRUCTIONS_TEMPLATE.format(now=format_datetime(local_now()), tz=settings.tz)


def format_channel_message(message: ChannelMessage) -> str:
    return f"[{format_datetime(message.created_at)}] {message.author_name}: {message.content}"


def get_turn_input(
    channel_messages: list[ChannelMessage], author_name: str, author_id: int, content: str
) -> str:
    sections = []
    if channel_messages:
        formatted_messages = "\n".join(format_channel_message(m) for m in channel_messages)
        sections.append(
            "Earlier messages in this channel, oldest first (context only):\n"
            f"<channel_context>\n{formatted_messages}\n</channel_context>"
        )
    sections.append(
        f"Message to reply to, from {author_name} ({mention(str(author_id))}):\n"
        f"<message>\n{content}\n</message>"
    )
    return "\n\n".join(sections)
