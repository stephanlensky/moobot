import asyncio
import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture

from moobot.discord.discord_bot import DiscordBot

BOT_USER = MagicMock(id=999)


@pytest.fixture
def command_handler(mocker: MockerFixture) -> AsyncMock:
    handler = AsyncMock()
    mocker.patch.dict(
        "moobot.discord.discord_bot._discord_bot_commands",
        {re.compile("^ping$", re.IGNORECASE): handler},
        clear=True,
    )
    return handler


@pytest.fixture
def bot(mocker: MockerFixture) -> DiscordBot:
    mocker.patch("moobot.discord.discord_bot.app_commands.CommandTree")
    mocker.patch("moobot.discord.discord_bot.get_async_scheduler")
    mocker.patch("moobot.discord.discord_bot.get_threadpool_scheduler")
    client = MagicMock()
    client.user = BOT_USER
    bot = DiscordBot(client)
    bot.agent_worker = MagicMock()
    return bot


BOT_ROLE = MagicMock(id=555)
BOT_ROLE.tags.bot_id = 999
OTHER_ROLE = MagicMock(id=556)
OTHER_ROLE.tags = None


def _get_message(
    content: str,
    mentions: list[MagicMock] | None = None,
    is_bot: bool = False,
    role_mentions: list[MagicMock] | None = None,
) -> MagicMock:
    message = MagicMock(
        content=content,
        mentions=mentions or [],
        role_mentions=role_mentions or [],
        mention_everyone=False,
    )
    message.author.bot = is_bot
    return message


@pytest.mark.parametrize(
    "message,is_command,is_agent",
    [
        (_get_message("<@999> what's coming up?", [BOT_USER]), False, True),
        (_get_message("hey <@!999>", [BOT_USER]), False, True),
        (_get_message("<@999> ping", [BOT_USER]), True, False),
        (_get_message("<@&555> what's coming up?", role_mentions=[BOT_ROLE]), False, True),
        (_get_message("<@&555> ping", role_mentions=[BOT_ROLE]), True, False),
        (_get_message("<@&556> what's coming up?", role_mentions=[OTHER_ROLE]), False, False),
        (_get_message("$ping"), True, False),
        (_get_message("$what's up <@999>", [BOT_USER]), False, False),
        (_get_message("$what's up"), False, False),
        (_get_message("@everyone ping"), False, False),
        (_get_message("hello there"), False, False),
        (_get_message("<@999> what's up?", [BOT_USER], is_bot=True), False, False),
    ],
)
def test_on_message__routes_to_command_or_agent(
    bot: DiscordBot,
    command_handler: AsyncMock,
    message: MagicMock,
    is_command: bool,
    is_agent: bool,
) -> None:
    asyncio.run(bot.on_message(message))

    assert command_handler.await_count == int(is_command)
    assert bot.agent_worker.queue_turn.call_count == int(is_agent)  # type: ignore[attr-defined]
