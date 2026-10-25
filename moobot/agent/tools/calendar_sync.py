from typing import Annotated

from agents import RunContextWrapper, function_tool

from moobot.agent.context import AgentContext
from moobot.calendar_sync import CALENDAR_SYNC_LABELS, has_calendar_sync
from moobot.db.models import GoogleCalendarType
from moobot.discord.views.agent_action import StartCalendarSyncView, StopCalendarSyncView

CalendarArg = Annotated[
    GoogleCalendarType,
    "Which calendar: 'events' for the user's event RSVPs, or 'birthdays' for everyone's saved"
    " birthdays.",
]


def queue_start_calendar_sync_view(context: AgentContext, calendar: GoogleCalendarType) -> str:
    label = CALENDAR_SYNC_LABELS[calendar]
    if has_calendar_sync(context.author_id, calendar):
        return (
            f"{context.author_name} already has {label} turned on. Nothing was attached. Use"
            " stop_calendar_sync if they want to turn it off."
        )
    context.views.append(
        StartCalendarSyncView(context.bot, context.author_id, context.message, calendar)
    )
    return (
        f"A button that starts setting up {label} will be attached to your reply. Clicking it DMs"
        " the user a Google authorization link, or turns it on right away if they've already"
        " authorized Google for another sync. Nothing happens until they click it."
    )


def queue_stop_calendar_sync_view(context: AgentContext, calendar: GoogleCalendarType) -> str:
    label = CALENDAR_SYNC_LABELS[calendar]
    if not has_calendar_sync(context.author_id, calendar):
        return f"{context.author_name} doesn't have {label} turned on. Nothing was attached."
    context.views.append(
        StopCalendarSyncView(context.bot, context.author_id, context.message, calendar)
    )
    return (
        f"A button that turns off {label} will be attached to your reply. Nothing changes until"
        " the user clicks it."
    )


@function_tool(
    description_override=(
        "Attach a button to your reply that sets up Google Calendar sync for the user you're"
        " replying to. Event sync puts the events they RSVP to on their Google Calendar; birthday"
        " sync puts everyone's saved birthdays on it. Doesn't change anything: the user has to"
        " click it."
    )
)
async def start_calendar_sync(
    context: RunContextWrapper[AgentContext], calendar: CalendarArg
) -> str:
    return queue_start_calendar_sync_view(context.context, calendar)


@function_tool(
    description_override=(
        "Attach a button to your reply that turns off Google Calendar sync for the user you're"
        " replying to. Doesn't change anything: the user has to click it."
    )
)
async def stop_calendar_sync(
    context: RunContextWrapper[AgentContext], calendar: CalendarArg
) -> str:
    return queue_stop_calendar_sync_view(context.context, calendar)
