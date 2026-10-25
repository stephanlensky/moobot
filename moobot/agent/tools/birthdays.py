import calendar
import json
import re
from datetime import date
from typing import Annotated, Any

from agents import RunContextWrapper, function_tool

from moobot.agent.context import AgentContext
from moobot.calendar_sync import (
    get_display_name,
    get_guild_member,
    handle_google_calendar_sync_on_birthday_change,
)
from moobot.db.crud import birthdays as birthday_crud
from moobot.db.session import Session
from moobot.util.discord import mention
from moobot.util.google import BIRTHDAY_START_YEAR
from moobot.util.time import today as local_today

USER_ID_PATTERN = re.compile(r"^(?:<@!?)?(\d+)>?$")

UserIdArg = Annotated[
    str | None,
    "Discord user id of the person whose birthday this is, from their <@user_id> mention. Leave"
    " it out for the user you're replying to.",
]


def format_birthday(month: int, day: int) -> str:
    return f"{calendar.month_name[month]} {day}"


def get_next_birthday(month: int, day: int, today: date) -> date:
    for year in (today.year, today.year + 1):
        birthday = date(year, month, min(day, calendar.monthrange(year, month)[1]))
        if birthday >= today:
            return birthday
    raise ValueError(f"no upcoming birthday for {month}/{day}")


def get_birthdays_data(context: AgentContext) -> list[dict[str, Any]]:
    today = local_today()
    with Session() as session:
        birthdays = [(int(b.user_id), b.month, b.day) for b in birthday_crud.get_birthdays(session)]

    birthdays_data = []
    for user_id, month, day in birthdays:
        next_birthday = get_next_birthday(month, day, today)
        birthdays_data.append(
            {
                "name": get_display_name(context.bot.client, user_id),
                "user": mention(str(user_id)),
                "birthday": format_birthday(month, day),
                "next_birthday": next_birthday.isoformat(),
                "days_until": (next_birthday - today).days,
            }
        )
    return sorted(birthdays_data, key=lambda b: b["days_until"])


@function_tool(
    description_override=(
        "Get everyone's saved birthdays, ordered by whose birthday is coming up next. Each one"
        " includes the person's name and mention, their birthday, the date of their next"
        " birthday and how many days away it is."
    )
)
async def get_birthdays(context: RunContextWrapper[AgentContext]) -> str:
    return json.dumps(get_birthdays_data(context.context))


def get_birthday_user(context: AgentContext, user_id: str | None) -> tuple[int, str] | str:
    if user_id is None:
        return context.author_id, context.author_name
    match = USER_ID_PATTERN.match(user_id.strip())
    member = get_guild_member(context.bot.client, int(match.group(1))) if match else None
    if member is None or member.bot:
        return (
            f"Error: {user_id!r} isn't a person in the server. Use the id from their <@user_id>"
            " mention, or ask who they mean."
        )
    return member.id, member.display_name


@function_tool(
    description_override=(
        "Save someone's birthday. Defaults to the user you're replying to; pass user_id to set"
        " someone else's. Only month and day are stored."
    )
)
async def set_birthday(
    context: RunContextWrapper[AgentContext],
    month: Annotated[int, "Month of the birthday, 1-12."],
    day: Annotated[int, "Day of the month of the birthday."],
    user_id: UserIdArg = None,
) -> str:
    birthday_user = get_birthday_user(context.context, user_id)
    if isinstance(birthday_user, str):
        return birthday_user
    birthday_user_id, name = birthday_user
    try:
        date(BIRTHDAY_START_YEAR, month, day)
    except ValueError:
        return f"Error: {month}/{day} isn't a real date. Nothing was saved."

    with Session() as session:
        birthday_crud.set_birthday(session, birthday_user_id, month, day)
    handle_google_calendar_sync_on_birthday_change(context.context.bot.client, birthday_user_id)
    return (
        f"Saved {name}'s birthday as {format_birthday(month, day)}. It's synced to everyone with"
        " Google Calendar birthday sync."
    )


@function_tool(
    description_override=(
        "Remove someone's saved birthday. Defaults to the user you're replying to; pass user_id to"
        " remove someone else's."
    )
)
async def clear_birthday(
    context: RunContextWrapper[AgentContext], user_id: UserIdArg = None
) -> str:
    birthday_user = get_birthday_user(context.context, user_id)
    if isinstance(birthday_user, str):
        return birthday_user
    birthday_user_id, name = birthday_user
    with Session() as session:
        deleted = birthday_crud.delete_birthday(session, birthday_user_id)
    if not deleted:
        return f"{name} doesn't have a saved birthday. Nothing was removed."
    handle_google_calendar_sync_on_birthday_change(context.context.bot.client, birthday_user_id)
    return f"Removed {name}'s birthday."
