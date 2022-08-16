import logging
from datetime import datetime
from pathlib import Path

import yaml

from moobot.db.models import MoobloomEvent
from moobot.db.session import Session

_logger = logging.getLogger(__name__)


def load_events_from_file(path: Path) -> None:
    with path.open("r", encoding="utf-8") as f:
        events = yaml.safe_load(f)["events"]

    with Session() as session:
        existing_event_names = {n[0] for n in session.query(MoobloomEvent.name).all()}

        added = 0
        for event in events:
            if event["name"] in existing_event_names:
                continue
            event["date"] = datetime.fromisoformat(event["date"])

            added += 1
            session.add(MoobloomEvent(**event))

        session.commit()

    _logger.info(f"Loaded {added} events from file")
