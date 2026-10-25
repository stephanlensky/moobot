from agents import Tool

from moobot.agent.tools.birthdays import clear_birthday, get_birthdays, set_birthday
from moobot.agent.tools.calendar_sync import start_calendar_sync, stop_calendar_sync
from moobot.agent.tools.event_actions import create_event, delete_event, update_event
from moobot.agent.tools.events import get_events

TOOLS: list[Tool] = [
    get_events,
    create_event,
    update_event,
    delete_event,
    get_birthdays,
    set_birthday,
    clear_birthday,
    start_calendar_sync,
    stop_calendar_sync,
]
