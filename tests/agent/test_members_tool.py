import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

from agents import FunctionTool
from agents.tool_context import ToolContext

from moobot.agent.context import AgentContext
from moobot.agent.tools.members import get_members


def _get_member(
    user_id: int,
    display_name: str,
    username: str,
    global_name: str | None = None,
    bot: bool = False,
) -> MagicMock:
    member = MagicMock(id=user_id, display_name=display_name, global_name=global_name, bot=bot)
    member.name = username
    return member


def _get_context() -> AgentContext:
    bot = MagicMock()
    guild = MagicMock()
    guild.members = [
        _get_member(1, "mikey", "mlai", global_name="Michael Lai"),
        _get_member(2, "Alicia", "alicia_s"),
        _get_member(3, "Moobot", "moobot", bot=True),
        _get_member(4, "Ben", "benjamin"),
    ]
    other_guild = MagicMock()
    other_guild.members = [guild.members[1]]
    bot.client.guilds = [guild, other_guild]
    return AgentContext(
        bot=bot, channel_id=1, author_id=2, author_name="Alicia", message=MagicMock()
    )


def _invoke(tool: FunctionTool, context: AgentContext, **arguments: Any) -> Any:
    tool_arguments = json.dumps(arguments)
    tool_context = ToolContext(
        context, tool_name=tool.name, tool_call_id="call_1", tool_arguments=tool_arguments
    )

    async def invoke() -> str:
        return str(await tool.on_invoke_tool(tool_context, tool_arguments))

    return json.loads(asyncio.run(invoke()))


def test_get_members__no_name__lists_people_sorted_without_bots_or_duplicates() -> None:
    result = _invoke(get_members, _get_context())

    assert result == [
        {"name": "Alicia", "username": "alicia_s", "user": "<@2>"},
        {"name": "Ben", "username": "benjamin", "user": "<@4>"},
        {"name": "mikey", "username": "mlai", "user": "<@1>"},
    ]


def test_get_members__name__matches_global_name_case_insensitively() -> None:
    result = _invoke(get_members, _get_context(), name=" MICHAEL ")

    assert result == [{"name": "mikey", "username": "mlai", "user": "<@1>"}]


def test_get_members__name__matches_username() -> None:
    result = _invoke(get_members, _get_context(), name="benj")

    assert result == [{"name": "Ben", "username": "benjamin", "user": "<@4>"}]


def test_get_members__name_matches_nobody__returns_empty_list() -> None:
    assert _invoke(get_members, _get_context(), name="zed") == []
