from __future__ import annotations

import asyncio
import logging
import re
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord
from agents import (
    ItemHelpers,
    MessageOutputItem,
    ReasoningItem,
    RunItem,
    ToolCallItem,
    ToolCallOutputItem,
)
from discord import Message
from sqlalchemy.exc import IntegrityError

from moobot.agent.agent import run_turn
from moobot.agent.context import AgentContext
from moobot.agent.history import get_channel_context, get_message_content
from moobot.agent.prompts import get_turn_input
from moobot.agent.transcript import get_transcript_start_index
from moobot.constants import (
    AGENT_EMPTY_OUTPUT_MESSAGE,
    AGENT_REPLY_ALLOWED_MENTIONS,
    AGENT_TURN_FAILED_MESSAGE,
    DISCORD_MESSAGE_LENGTH_LIMIT,
)
from moobot.db.crud.agent import (
    cancel_cleared_running_turns,
    create_turn,
    get_active_conversation,
    get_channel_ids_with_queued_turns,
    get_next_queued_turn,
    get_or_create_active_conversation,
    reset_running_turns,
    set_last_seen_message_id,
    set_turn_completed,
    set_turn_failed,
    set_turn_running,
)
from moobot.db.session import Session
from moobot.storage import get_transcript, set_transcript

if TYPE_CHECKING:
    from moobot.discord.discord_bot import DiscordBot
    from moobot.discord.views.agent_action import AgentActionView

_logger = logging.getLogger(__name__)

CODE_FENCE = "```"
CODE_FENCE_PATTERN = re.compile(r"```([\w+#.-]{0,32})")


@dataclass
class Turn:
    id: int
    conversation_id: int
    transcript_key: str
    last_seen_message_id: int | None
    message_id: int
    author_id: int
    author_name: str
    content: str


def get_channel_log_prefix(channel_id: int) -> str:
    return f"[channel {channel_id}]"


def get_turn_log_prefix(channel_id: int, turn_id: int) -> str:
    return f"{get_channel_log_prefix(channel_id)} [turn {turn_id}]"


def log_lines(prefix: str, text: str) -> None:
    _logger.info("\n".join(f"{prefix} {line}" for line in text.splitlines() or [""]))


def log_channel(channel_id: int, text: str) -> None:
    log_lines(get_channel_log_prefix(channel_id), text)


def log_turn(channel_id: int, turn_id: int, text: str) -> None:
    log_lines(get_turn_log_prefix(channel_id, turn_id), text)


def get_run_item_text(item: RunItem) -> str:
    if isinstance(item, ToolCallItem):
        raw_item = item.raw_item
        arguments = (
            raw_item.get("arguments")
            if isinstance(raw_item, dict)
            else getattr(raw_item, "arguments", None)
        )
        return f"Tool call {item.tool_name} ({item.call_id}): {arguments}"
    if isinstance(item, ToolCallOutputItem):
        return f"Tool output ({item.call_id}): {item.output}"
    if isinstance(item, MessageOutputItem):
        return f"Agent message: {ItemHelpers.text_message_output(item)}"
    if isinstance(item, ReasoningItem):
        reasoning = [summary.text for summary in item.raw_item.summary]
        reasoning.extend(content.text for content in item.raw_item.content or [])
        return f"Agent reasoning: {'\n'.join(reasoning)}"
    return f"Run item {item.type}: {item.to_input_item()}"


def log_run_items(channel_id: int, turn_id: int, items: list[RunItem]) -> None:
    for item in items:
        log_turn(channel_id, turn_id, get_run_item_text(item))


def get_open_code_fence(text: str) -> str | None:
    open_fence = None
    for line in text.split("\n"):
        languages = CODE_FENCE_PATTERN.findall(line)
        if len(languages) % 2 == 1:
            open_fence = None if open_fence is not None else f"{CODE_FENCE}{languages[-1]}"
    return open_fence


def get_split_start(text: str) -> int:
    first_line_end = text.find("\n")
    if first_line_end > 0 and get_open_code_fence(text[:first_line_end]) is not None:
        return first_line_end
    return 0


def get_split_index(text: str, limit: int) -> int:
    start = get_split_start(text)
    split_index = text.rfind("\n", start + 1, limit + 1)
    if split_index <= start:
        return limit
    chunk = text[:split_index]
    last_line_start = chunk.rfind("\n")
    if (
        last_line_start > start
        and get_open_code_fence(chunk) is not None
        and get_open_code_fence(chunk[:last_line_start]) is None
    ):
        return last_line_start
    return split_index


def split_message(text: str, limit: int = DISCORD_MESSAGE_LENGTH_LIMIT) -> list[str]:
    closing_fence = f"\n{CODE_FENCE}"
    chunks = []
    while len(text) > limit:
        split_index = get_split_index(text, limit)
        if get_open_code_fence(text[:split_index]) is not None:
            split_index = get_split_index(text, limit - len(closing_fence))
        chunk, text = text[:split_index], text[split_index:].lstrip("\n")
        open_fence = get_open_code_fence(chunk)
        if open_fence is not None:
            chunk += closing_fence
            text = f"{open_fence}\n{text}"
        chunks.append(chunk)
    chunks.append(text)
    return [chunk for chunk in chunks if chunk.strip()]


async def send_chunk(
    message: Message, chunk: str, is_first: bool, view: AgentActionView | None
) -> Message:
    kwargs: dict[str, Any] = {"allowed_mentions": AGENT_REPLY_ALLOWED_MENTIONS}
    if view is not None:
        kwargs["view"] = view
    if is_first:
        response = await message.reply(chunk, **kwargs)
    else:
        response = await message.channel.send(chunk, **kwargs)
    if view is not None:
        view.message = response
    return response


async def send_reply(
    message: Message, text: str, views: Sequence[AgentActionView] = ()
) -> list[Message]:
    chunks = split_message(text)
    response_messages = []
    for index, chunk in enumerate(chunks):
        view = views[0] if views and index == len(chunks) - 1 else None
        response_messages.append(await send_chunk(message, chunk, index == 0, view))
    for view in views[1:]:
        response_messages.append(await send_chunk(message, view.label, False, view))
    return response_messages


def get_views_text(views: Sequence[AgentActionView]) -> str:
    return ", ".join(
        f"{view.label} (message {view.message.id if view.message else None})" for view in views
    )


class AgentWorker:
    def __init__(self, bot: DiscordBot) -> None:
        self.bot = bot
        self.tasks: dict[int, asyncio.Task[None]] = {}
        self.transcript_locks: dict[int, asyncio.Lock] = {}
        self.recovered = False

    def get_bot_user(self) -> discord.ClientUser:
        if self.bot.client.user is None:
            raise ValueError("Bot user is not set")
        return self.bot.client.user

    def get_transcript_lock(self, channel_id: int) -> asyncio.Lock:
        return self.transcript_locks.setdefault(channel_id, asyncio.Lock())

    async def add_transcript_note(self, channel_id: int, text: str) -> None:
        try:
            async with self.get_transcript_lock(channel_id):
                with Session() as session:
                    conversation = get_active_conversation(session, channel_id)
                    transcript_key = conversation.transcript_key if conversation else None
                if transcript_key is None:
                    log_channel(
                        channel_id, f"No active conversation, skipping transcript note:\n{text}"
                    )
                    return
                transcript = await get_transcript(transcript_key)
                await set_transcript(
                    transcript_key, [*transcript, {"role": "user", "content": text}]
                )
            log_channel(channel_id, f"Added transcript note to {transcript_key}:\n{text}")
        except Exception:
            _logger.exception(
                f"{get_channel_log_prefix(channel_id)} Failed to add transcript note:\n{text}"
            )

    def queue_turn(self, message: Message) -> None:
        channel_id = message.channel.id
        content = get_message_content(message, self.get_bot_user())
        try:
            with Session() as session:
                conversation = get_or_create_active_conversation(session, channel_id)
                turn_id = create_turn(
                    session,
                    conversation_id=conversation.id,
                    message_id=message.id,
                    author_id=message.author.id,
                    author_name=message.author.display_name,
                    content=content,
                ).id
        except IntegrityError:
            _logger.warning(
                f"[channel {channel_id}] Message {message.id} is already queued, ignoring it"
            )
            return
        log_turn(
            channel_id,
            turn_id,
            f"Queued message {message.id} from {message.author.display_name}"
            f" ({message.author.id}):\n{content}",
        )
        self.start_worker(channel_id)

    def start_worker(self, channel_id: int) -> None:
        task = self.tasks.get(channel_id)
        if task is not None and not task.done():
            return
        self.tasks[channel_id] = asyncio.create_task(self.run_worker(channel_id))

    def start_queued_workers(self) -> None:
        with Session() as session:
            if not self.recovered:
                reset_count = reset_running_turns(session)
                cancelled_count = cancel_cleared_running_turns(session)
                _logger.info(
                    f"Reset {reset_count} running agent turns to queued and cancelled"
                    f" {cancelled_count} running agent turns on cleared conversations"
                )
                self.recovered = True
            channel_ids = get_channel_ids_with_queued_turns(session)
        _logger.info(f"Starting agent workers for channels with queued turns: {channel_ids}")
        for channel_id in channel_ids:
            self.start_worker(channel_id)

    async def run_worker(self, channel_id: int) -> None:
        try:
            while (turn := self.start_next_turn(channel_id)) is not None:
                await self.run_queued_turn(channel_id, turn)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception(f"[channel {channel_id}] Agent worker stopped unexpectedly")

    def start_next_turn(self, channel_id: int) -> Turn | None:
        with Session() as session:
            conversation = get_active_conversation(session, channel_id)
            if conversation is None:
                return None
            db_turn = get_next_queued_turn(session, conversation.id)
            if db_turn is None:
                return None
            turn = Turn(
                id=db_turn.id,
                conversation_id=conversation.id,
                transcript_key=conversation.transcript_key,
                last_seen_message_id=(
                    int(conversation.last_seen_message_id)
                    if conversation.last_seen_message_id is not None
                    else None
                ),
                message_id=int(db_turn.message_id),
                author_id=int(db_turn.author_id),
                author_name=db_turn.author_name,
                content=db_turn.content,
            )
            set_turn_running(session, turn.id)
        return turn

    async def run_queued_turn(self, channel_id: int, turn: Turn) -> None:
        channel = self.bot.client.get_partial_messageable(channel_id)
        message: Message | None = None
        prompt: str | None = None
        replied = False
        try:
            try:
                message = await channel.fetch_message(turn.message_id)
            except discord.NotFound:
                log_turn(channel_id, turn.id, f"Message {turn.message_id} was deleted, skipping")
                with Session() as session:
                    set_turn_failed(session, turn.id, "The message was deleted before the turn ran")
                return

            async with self.get_transcript_lock(channel_id):
                async with channel.typing():
                    transcript = await get_transcript(turn.transcript_key)
                    transcript_start_index = get_transcript_start_index(transcript)
                    channel_messages = await get_channel_context(
                        channel, message, turn.last_seen_message_id, self.get_bot_user()
                    )
                    log_turn(
                        channel_id,
                        turn.id,
                        f"Started turn for message {turn.message_id} with {len(transcript)}"
                        f" transcript items and {len(channel_messages)} channel context messages",
                    )
                    if transcript_start_index > 0:
                        log_turn(
                            channel_id,
                            turn.id,
                            f"Trimmed {transcript_start_index} older transcript items from the model"
                            " input",
                        )
                    prompt = get_turn_input(
                        channel_messages,
                        turn.author_name,
                        message.author.name,
                        turn.author_id,
                        turn.content,
                    )
                    log_turn(channel_id, turn.id, f"Prompt:\n{prompt}")
                    context = AgentContext(
                        bot=self.bot,
                        channel_id=channel_id,
                        author_id=turn.author_id,
                        author_name=turn.author_name,
                        message=message,
                    )
                    result = await run_turn(transcript[transcript_start_index:], prompt, context)
                    log_run_items(channel_id, turn.id, result.new_items)
                    output = str(result.final_output or "")
                    if not output.strip():
                        log_turn(
                            channel_id, turn.id, "Agent returned an empty reply, using the fallback"
                        )
                        output = AGENT_EMPTY_OUTPUT_MESSAGE

                response_messages = await send_reply(message, output, context.views)
                replied = True
                response_message_ids = [response.id for response in response_messages]
                log_turn(channel_id, turn.id, f"Replied {response_message_ids}:\n{output}")
                if context.views:
                    log_turn(
                        channel_id, turn.id, f"Attached views: {get_views_text(context.views)}"
                    )
                await set_transcript(
                    turn.transcript_key,
                    [*transcript[:transcript_start_index], *result.to_input_list()],
                )
            with Session() as session:
                set_last_seen_message_id(session, turn.conversation_id, turn.message_id)
                set_turn_completed(
                    session,
                    turn.id,
                    prompt=prompt,
                    output=output,
                    response_message_id=response_message_ids[-1],
                )
            log_turn(channel_id, turn.id, "Completed turn")
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception(f"{get_turn_log_prefix(channel_id, turn.id)} Turn failed")
            with Session() as session:
                set_turn_failed(session, turn.id, traceback.format_exc(), prompt)
            if message is not None and not replied:
                await self.send_failure_reply(channel_id, turn.id, message)

    async def send_failure_reply(self, channel_id: int, turn_id: int, message: Message) -> None:
        try:
            await message.reply(
                AGENT_TURN_FAILED_MESSAGE.format(mention=message.author.mention),
                allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS,
            )
        except discord.HTTPException:
            _logger.exception(
                f"{get_turn_log_prefix(channel_id, turn_id)} Failed to send the failure reply"
            )
