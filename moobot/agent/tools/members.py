import json
from typing import Annotated, Any

from agents import RunContextWrapper, function_tool
from discord import Member

from moobot.agent.context import AgentContext
from moobot.util.discord import mention


def get_member_names(member: Member) -> list[str]:
    return [name for name in (member.display_name, member.global_name, member.name) if name]


def get_members_data(context: AgentContext, name: str | None) -> list[dict[str, Any]]:
    members: dict[int, Member] = {}
    for guild in context.bot.client.guilds:
        for member in guild.members:
            if not member.bot:
                members.setdefault(member.id, member)

    if name is not None:
        query = name.strip().casefold()
        members = {
            member_id: member
            for member_id, member in members.items()
            if any(query in member_name.casefold() for member_name in get_member_names(member))
        }

    members_data = [
        {"name": member.display_name, "username": member.name, "user": mention(str(member.id))}
        for member in members.values()
    ]
    return sorted(members_data, key=lambda m: m["name"].casefold())


@function_tool(
    description_override=(
        "List the people in the server, with each one's display name, username and <@user_id>"
        " mention. Use it to find someone's user id from their name. Pass name to only get people"
        " whose display name, global name or username contains it (case-insensitive), e.g. a"
        " first name."
    )
)
async def get_members(
    context: RunContextWrapper[AgentContext],
    name: Annotated[
        str | None, "Part of a name to search for. Leave it out to list everyone."
    ] = None,
) -> str:
    return json.dumps(get_members_data(context.context, name))
