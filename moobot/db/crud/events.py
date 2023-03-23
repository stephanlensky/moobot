from sqlalchemy.orm import Session

from moobot.db.models import MoobloomEvent


def get_event_by_id(
    session: Session, id: int, include_deleted: bool = False
) -> MoobloomEvent | None:
    query = session.query(MoobloomEvent).filter(MoobloomEvent.id == id)
    if not include_deleted:
        query.filter(MoobloomEvent.deleted == False)

    return query.one_or_none()


def get_event_by_name(
    session: Session, name: str, include_deleted: bool = False
) -> MoobloomEvent | None:
    query = session.query(MoobloomEvent).filter(MoobloomEvent.name == name)
    if not include_deleted:
        query.filter(MoobloomEvent.deleted == False)

    return query.first()
