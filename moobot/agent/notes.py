from discord.abc import User

from moobot.agent.prompts import format_author
from moobot.constants import AGENT_TRANSCRIPT_NOTE_PREFIX
from moobot.db.models import MoobloomEvent
from moobot.util.discord import channel_mention
from moobot.util.format import format_event_duration


def get_event_channel(event: MoobloomEvent) -> str:
    if event.channel_id:
        return channel_mention(event.channel_id)
    if event.channel_name:
        return f"#{event.channel_name}"
    return "none"


def get_event_details(event: MoobloomEvent) -> str:
    when = format_event_duration(event.start_date, event.start_time, event.end_date, event.end_time)
    return (
        f"{when}, location: {event.location or 'none'}, channel: {get_event_channel(event)},"
        f" url: {event.url or 'none'}, description: {event.description or 'none'}"
    )


def get_note_author(user: User) -> str:
    return format_author(user.display_name, user.name, user.id)


def get_event_note(user: User, action: str, event: MoobloomEvent) -> str:
    return (
        f'{AGENT_TRANSCRIPT_NOTE_PREFIX} {get_note_author(user)} {action} the event "{event.name}"'
        f" (id {event.id}): {get_event_details(event)}"
    )


def get_delete_cancelled_note(user: User, event_id: int, event_name: str) -> str:
    return (
        f"{AGENT_TRANSCRIPT_NOTE_PREFIX} {get_note_author(user)} clicked Cancel instead of deleting"
        f' the event "{event_name}" (id {event_id}), so it was not deleted.'
    )
