import logging

from discord import Interaction
from discord.app_commands import Choice
from sqlalchemy import desc
from sqlalchemy.orm import Session as SessionCls

from moobot.db.crud.events import get_event_by_id, get_event_by_name
from moobot.db.models import MoobloomEvent
from moobot.db.session import Session
from moobot.util.format import format_event_duration

_logger = logging.getLogger(__name__)

# the Discord API rejects the whole autocomplete response if any choice name exceeds this
MAX_CHOICE_NAME_LEN = 100
MAX_CHOICES = 25


def _format_event_choice_name(event: MoobloomEvent) -> str:
    # choice names must be unique -- assume that name + duration is likely to be unique for our data
    duration = format_event_duration(
        event.start_date, event.start_time, event.end_date, event.end_time
    )
    name = f"{event.name} - {duration}"
    if len(name) <= MAX_CHOICE_NAME_LEN:
        return name

    # truncate the event name rather than the duration, since the duration is what disambiguates
    # two events sharing a name
    budget = MAX_CHOICE_NAME_LEN - len(f" - {duration}") - 1  # 1 for the ellipsis
    if budget <= 0:
        # pathological case: the duration alone fills the budget, so just clip the whole thing
        return name[: MAX_CHOICE_NAME_LEN - 1] + "…"
    return f"{event.name[:budget]}… - {duration}"


async def event_autocomplete(interaction: Interaction, current: str) -> list[Choice]:
    _logger.info(f"Received event autocomplete request (current={current!r})")
    try:
        with Session() as session:
            events: list[MoobloomEvent] = (
                session.query(MoobloomEvent)
                .filter(MoobloomEvent.deleted == False)
                .order_by(desc(MoobloomEvent.id))
                .all()
            )

        named = ((event, _format_event_choice_name(event)) for event in events)
        choices = [
            Choice(name=choice_name, value=str(event.id))
            for event, choice_name in named
            if choice_name.lower().startswith(current.lower())
        ][:MAX_CHOICES]
    except Exception:
        # discord.py swallows autocomplete exceptions into the `discord.app_commands.tree` logger,
        # which we don't configure a handler for -- log here so failures are actually visible
        _logger.exception("Failed to build event autocomplete choices")
        raise

    _logger.info(f"Returning {len(choices)} autocomplete choices (of {len(events)} events)")
    return choices


def get_event_from_option(session: SessionCls, event_arg: str) -> MoobloomEvent | None:
    # if arg is a valid PK ID (if user selected an auto-complete choice)
    try:
        event_id = int(event_arg)
        event = get_event_by_id(session, event_id)
        if event is not None:
            return event
    except ValueError:
        pass

    # otherwise they manually typed something, try matching by name
    return get_event_by_name(session, event_arg)
