from collections.abc import Generator
from datetime import date

import pytest
from sqlalchemy.orm import Session, sessionmaker

from moobot.db.crud.events import get_event_by_id, get_event_by_name
from moobot.db.models import MoobloomEvent


@pytest.fixture
def session(test_db_session: sessionmaker[Session]) -> Generator[Session]:
    with test_db_session() as session:
        yield session


def _create_event(session: Session, name: str, deleted: bool) -> MoobloomEvent:
    event = MoobloomEvent(
        name=name, start_date=date(2026, 10, 25), end_date=date(2026, 10, 25), deleted=deleted
    )
    session.add(event)
    session.commit()
    return event


@pytest.mark.parametrize("include_deleted,found", [(False, False), (True, True)])
def test_get_event_by_id__deleted_event__only_found_when_included(
    session: Session, include_deleted: bool, found: bool
) -> None:
    event = _create_event(session, "Hayride", deleted=True)

    assert (get_event_by_id(session, event.id, include_deleted) is not None) == found


@pytest.mark.parametrize("include_deleted,found", [(False, False), (True, True)])
def test_get_event_by_name__deleted_event__only_found_when_included(
    session: Session, include_deleted: bool, found: bool
) -> None:
    _create_event(session, "Hayride", deleted=True)

    assert (get_event_by_name(session, "Hayride", include_deleted) is not None) == found


def test_get_event_by_name__deleted_and_active_events__returns_active_event(
    session: Session,
) -> None:
    _create_event(session, "Hayride", deleted=True)
    active = _create_event(session, "Hayride", deleted=False)

    event = get_event_by_name(session, "Hayride")

    assert event is not None
    assert event.id == active.id
