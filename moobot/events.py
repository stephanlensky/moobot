import logging
from pathlib import Path

import discord
import yaml
from discord import Message

from moobot.db.models import MoobloomEvent
from moobot.db.session import Session
from moobot.settings import get_settings

settings = get_settings()

_logger = logging.getLogger(__name__)


def load_events_from_file(client: discord.Client, path: Path) -> None:
    with path.open("r", encoding="utf-8") as f:
        events = yaml.safe_load(f)["events"]

    with Session() as session:
        existing_event_names = {n[0] for n in session.query(MoobloomEvent.name).all()}

    new_events = []
    for event in events:
        if event["name"] in existing_event_names:
            continue

        _logger.info(f"Found event {event['name']}")
        new_events.append(MoobloomEvent.parse_obj(event))

    for event in new_events:
        create_event(client, event)

    _logger.info(f"Loaded {len(new_events)} events from file")


def create_event(client: discord.Client, event: MoobloomEvent) -> None:
    with Session(expire_on_commit=False) as session:
        session.add(event)
        session.commit()

    update_calendar_message(client)
    send_event_announcement(client, event)
    create_event_channel(client, event)


def get_calendar_message(client: discord.Client) -> Message | None:
    pass


def update_calendar_message(client: discord.Client) -> None:
    pass


def send_event_announcement(client: discord.Client, event: MoobloomEvent) -> None:
    pass


def create_event_channel(client: discord.Client, event: MoobloomEvent) -> None:
    pass
