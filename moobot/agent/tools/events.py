import json
from typing import Annotated, Any

from agents import RunContextWrapper, function_tool
from sqlalchemy.orm import Session as SessionCls
from sqlalchemy.orm import selectinload

from moobot.agent.context import AgentContext
from moobot.db.models import MoobloomEvent, MoobloomEventAttendanceType
from moobot.db.session import Session
from moobot.util.discord import channel_mention
from moobot.util.format import format_event_duration
from moobot.util.time import today as local_today


def get_event_data(event: MoobloomEvent) -> dict[str, Any]:
    rsvp_counts = {attendance_type.value: 0 for attendance_type in MoobloomEventAttendanceType}
    for rsvp in event.rsvps:
        rsvp_counts[rsvp.attendance_type] += 1

    return {
        "id": event.id,
        "name": event.name,
        "when": format_event_duration(
            event.start_date, event.start_time, event.end_date, event.end_time
        ),
        "start_date": event.start_date.isoformat(),
        "start_time": event.start_time.strftime("%H:%M") if event.start_time else None,
        "end_date": event.end_date.isoformat(),
        "end_time": event.end_time.strftime("%H:%M") if event.end_time else None,
        "location": event.location,
        "description": event.description,
        "url": event.url,
        "channel": channel_mention(event.channel_id) if event.channel_id else None,
        "rsvp_counts": rsvp_counts,
    }


def get_events_data(
    session: SessionCls, name: str | None = None, include_past: bool = False
) -> list[dict[str, Any]]:
    query = (
        session.query(MoobloomEvent)
        .filter(MoobloomEvent.deleted == False)
        .options(selectinload(MoobloomEvent.rsvps))
    )
    if name:
        query = query.filter(MoobloomEvent.name.ilike(f"%{name}%"))
    if not include_past:
        query = query.filter(MoobloomEvent.end_date >= local_today())

    events = query.order_by(MoobloomEvent.start_date, MoobloomEvent.start_time).all()
    return [get_event_data(event) for event in events]


@function_tool(
    description_override=(
        "Get Moobloom events, ordered by start date. By default returns upcoming and ongoing"
        " events. Each event includes its date and time ('when' is a ready-to-use summary;"
        " times are local), location, description, URL, private event channel and RSVP counts"
        " by attendance type."
    )
)
async def get_events(
    context: RunContextWrapper[AgentContext],
    name: Annotated[
        str | None, "Case-insensitive search for events whose name contains this text."
    ] = None,
    include_past: Annotated[bool, "Also include events that have already ended."] = False,
) -> str:
    with Session() as session:
        return json.dumps(get_events_data(session, name, include_past))
