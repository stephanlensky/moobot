from discord import Interaction
from discord.app_commands import Choice
from sqlalchemy import desc
from sqlalchemy.orm import Session as SessionCls

from moobot.db.models import MoobloomEvent
from moobot.db.session import Session
from moobot.util.format import format_event_duration


def _format_event_choice_name(event: MoobloomEvent) -> str:
    # choice names must be unique -- assume that name + duration is likely to be unique for our data
    return (
        f"{event.name} -"
        f" {format_event_duration(event.start_date, event.start_time, event.end_date, event.end_time)}"
    )


async def event_autocomplete(interaction: Interaction, current: str) -> list[Choice]:
    with Session() as session:
        events: list[MoobloomEvent] = (
            session.query(MoobloomEvent).order_by(desc(MoobloomEvent.id)).all()
        )

    # discord API limits to 25 choices
    return [
        Choice(name=_format_event_choice_name(event), value=str(event.id))
        for event in events
        if _format_event_choice_name(event).lower().startswith(current.lower())
    ][:25]


def get_event_from_option(session: SessionCls, event_arg: str) -> MoobloomEvent | None:
    # if arg is a valid PK ID (if user selected an auto-complete choice)
    try:
        event_id = int(event_arg)
        event = session.query(MoobloomEvent).filter(MoobloomEvent.id == event_id).one_or_none()
        if event is not None:
            return event
    except ValueError:
        pass

    # otherwise they manually typed something, try matching by name
    return session.query(MoobloomEvent).filter(MoobloomEvent.name == event_arg).first()
