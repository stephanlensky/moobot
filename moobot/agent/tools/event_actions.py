from typing import Annotated

from agents import RunContextWrapper, function_tool

from moobot.agent.context import AgentContext
from moobot.db.crud.events import get_event_by_id
from moobot.db.session import Session
from moobot.discord.views.agent_action import (
    CreateEventView,
    DeleteEventView,
    EventFields,
    UpdateEventView,
)
from moobot.discord.views.event_modal import parse_event_time

EVENT_FIELD_NAMES = {
    "name": "name",
    "time": "time",
    "location": "location",
    "channel_name": "channel name",
    "description": "description",
    "url": "url",
    "image_url": "image url",
}

NameArg = Annotated[str | None, "The event name."]
TimeArg = Annotated[
    str | None,
    "When the event happens, in local time, as free text like 'September 21', '9/21 7pm' or"
    " '9/21 7pm to 10pm'. Use 'to' between the start and the end.",
]
LocationArg = Annotated[str | None, "Where the event happens."]
ChannelNameArg = Annotated[
    str | None, "Name for a private Discord channel for the event, if one should be created."
]
DescriptionArg = Annotated[str | None, "Description of the event."]
UrlArg = Annotated[str | None, "Link to a web page for the event."]
ImageUrlArg = Annotated[str | None, "Link to an image for the event."]
EventIdArg = Annotated[int, "The event id, from get_events."]


def get_event_fields(
    name: str | None,
    time: str | None,
    location: str | None,
    channel_name: str | None,
    description: str | None,
    url: str | None,
    image_url: str | None,
) -> EventFields:
    return EventFields(
        name=name,
        time=parse_event_time(time) if time else None,
        location=location,
        channel_name=channel_name,
        description=description,
        url=url,
        image_url=image_url,
    )


def get_time_error(time: str | None, error: ValueError) -> str:
    return (
        f"Error: couldn't understand the time {time!r} ({error}). Nothing was attached. Try again"
        " with a time like 'September 21', '9/21 7pm' or '9/21 7pm to 10pm', or ask the user."
    )


def get_event_not_found_error(event_id: int) -> str:
    return (
        f"Error: there's no event with id {event_id}. Nothing was attached. Use get_events to look"
        " up the event id."
    )


def get_blank_field_names(fields: EventFields) -> list[str]:
    return [label for field, label in EVENT_FIELD_NAMES.items() if not getattr(fields, field)]


def queue_create_event_view(context: AgentContext, fields: EventFields) -> str:
    context.views.append(CreateEventView(context.bot, context.author_id, context.message, fields))
    result = (
        "A button that opens a pre-filled event form will be attached to your reply. Nothing is"
        " created until the user submits the form."
    )
    if blank_field_names := get_blank_field_names(fields):
        result += f" Left blank for the user to fill in: {', '.join(blank_field_names)}."
    return result


def queue_update_event_view(context: AgentContext, event_id: int, fields: EventFields) -> str:
    with Session() as session:
        event = get_event_by_id(session, event_id)
        if event is None:
            return get_event_not_found_error(event_id)
        event_name = event.name
        current_channel_name = event.channel_name

    if (
        fields.channel_name
        and current_channel_name
        and fields.channel_name.removeprefix("#") != current_channel_name
    ):
        return (
            f"Error: event {event_name} already has the channel #{current_channel_name}, and"
            " channel names can't be changed. Nothing was attached."
        )

    context.views.append(
        UpdateEventView(
            context.bot, context.author_id, context.message, event_id, event_name, fields
        )
    )
    return (
        f"A button that opens the update form for {event_name}, pre-filled with its current"
        " details and your changes, will be attached to your reply. Nothing changes until the user"
        " submits the form."
    )


def queue_delete_event_view(context: AgentContext, event_id: int) -> str:
    with Session() as session:
        event = get_event_by_id(session, event_id)
        if event is None:
            return get_event_not_found_error(event_id)
        event_name = event.name

    context.views.append(
        DeleteEventView(context.bot, context.author_id, context.message, event_id, event_name)
    )
    return (
        f"Delete and Cancel buttons for {event_name} will be attached to your reply. Nothing is"
        " deleted until the user clicks Delete."
    )


@function_tool(
    description_override=(
        "Attach a button to your reply that opens the event creation form, pre-filled with the"
        " details you pass. Doesn't create anything: the user finishes in the form. Only pass"
        " details the user gave you and leave the rest out."
    )
)
async def create_event(
    context: RunContextWrapper[AgentContext],
    name: NameArg = None,
    time: TimeArg = None,
    location: LocationArg = None,
    channel_name: ChannelNameArg = None,
    description: DescriptionArg = None,
    url: UrlArg = None,
    image_url: ImageUrlArg = None,
) -> str:
    try:
        fields = get_event_fields(name, time, location, channel_name, description, url, image_url)
    except ValueError as e:
        return get_time_error(time, e)
    return queue_create_event_view(context.context, fields)


@function_tool(
    description_override=(
        "Attach a button to your reply that opens the update form for an existing event,"
        " pre-filled with its current details and the changes you pass. Doesn't change anything:"
        " the user finishes in the form. Leave out fields that aren't changing."
    )
)
async def update_event(
    context: RunContextWrapper[AgentContext],
    event_id: EventIdArg,
    name: NameArg = None,
    time: TimeArg = None,
    location: LocationArg = None,
    channel_name: ChannelNameArg = None,
    description: DescriptionArg = None,
    url: UrlArg = None,
    image_url: ImageUrlArg = None,
) -> str:
    try:
        fields = get_event_fields(name, time, location, channel_name, description, url, image_url)
    except ValueError as e:
        return get_time_error(time, e)
    return queue_update_event_view(context.context, event_id, fields)


@function_tool(
    description_override=(
        "Attach Delete and Cancel buttons for an existing event to your reply. Doesn't delete"
        " anything: the user has to click Delete."
    )
)
async def delete_event(context: RunContextWrapper[AgentContext], event_id: EventIdArg) -> str:
    return queue_delete_event_view(context.context, event_id)
