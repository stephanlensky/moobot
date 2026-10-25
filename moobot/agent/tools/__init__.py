from agents import Tool

from moobot.agent.tools.event_actions import create_event, delete_event, update_event
from moobot.agent.tools.events import get_events

TOOLS: list[Tool] = [get_events, create_event, update_event, delete_event]
