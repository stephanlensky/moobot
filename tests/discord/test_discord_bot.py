import asyncio
from unittest.mock import MagicMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from pytest_mock import MockerFixture

from moobot.discord.discord_bot import DiscordBot

BOT_USER = MagicMock(id=999)


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
    "message,is_agent",
    [
        (_get_message("<@999> what's coming up?", [BOT_USER]), True),
        (_get_message("hey <@!999>", [BOT_USER]), True),
        (_get_message("<@&555> what's coming up?", role_mentions=[BOT_ROLE]), True),
        (_get_message("<@&556> what's coming up?", role_mentions=[OTHER_ROLE]), False),
        (_get_message("@everyone what's up?"), False),
        (_get_message("hello there"), False),
        (_get_message("<@999> what's up?", [BOT_USER], is_bot=True), False),
    ],
)
def test_on_message__routes_mentions_to_agent(
    bot: DiscordBot, message: MagicMock, is_agent: bool
) -> None:
    asyncio.run(bot.on_message(message))

    assert bot.agent_worker.queue_turn.call_count == int(is_agent)  # type: ignore[attr-defined]


def test_on_ready__called_again__registers_each_scheduler_job_once(mocker: MockerFixture) -> None:
    mocker.patch("moobot.discord.discord_bot.app_commands.CommandTree")
    threadpool_scheduler = BackgroundScheduler()
    mocker.patch(
        "moobot.discord.discord_bot.get_threadpool_scheduler", return_value=threadpool_scheduler
    )

    async def get_job_ids_after_two_on_ready_calls() -> tuple[list[str], list[str]]:
        scheduler = AsyncIOScheduler()
        mocker.patch("moobot.discord.discord_bot.get_async_scheduler", return_value=scheduler)
        scheduler.start(paused=True)
        threadpool_scheduler.start(paused=True)
        try:
            bot = DiscordBot(MagicMock(user=BOT_USER, guilds=[]))
            bot.agent_worker = MagicMock()
            await bot.on_ready()
            await bot.on_ready()
            return (
                [job.id for job in scheduler.get_jobs()],
                [job.id for job in threadpool_scheduler.get_jobs()],
            )
        finally:
            scheduler.shutdown(wait=False)
            threadpool_scheduler.shutdown(wait=False)

    assert asyncio.run(get_job_ids_after_two_on_ready_calls()) == (
        ["initialize_events"],
        ["complete_unfinished_google_calendar_setups"],
    )
