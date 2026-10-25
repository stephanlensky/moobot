from sqlalchemy.orm import Session

from moobot.db.models import (
    GoogleApiAuthSession,
    GoogleApiUser,
    GoogleCalendar,
    GoogleCalendarSync,
    GoogleCalendarType,
)


def create_auth_session(
    session: Session,
    state: str,
    code_verifier: str,
    user_id: int,
    calendar_type: GoogleCalendarType,
    commit: bool = True,
) -> None:
    session.add(
        GoogleApiAuthSession(
            state=state,
            code_verifier=code_verifier,
            user_id=str(user_id),
            calendar_type=calendar_type,
        )
    )
    if commit:
        session.commit()


def get_auth_session_by_state(session: Session, state: str) -> GoogleApiAuthSession | None:
    return session.query(GoogleApiAuthSession).filter(GoogleApiAuthSession.state == state).first()


def set_api_user(
    session: Session,
    user_id: int,
    token: str,
    refresh_token: str,
    token_uri: str,
    scopes: str,
    commit: bool = True,
) -> None:
    api_user = get_api_user_by_user_id(session, user_id)
    if api_user is None:
        api_user = GoogleApiUser(user_id=str(user_id))
        session.add(api_user)
    api_user.token = token
    api_user.refresh_token = refresh_token
    api_user.token_uri = token_uri
    api_user.scopes = scopes
    if commit:
        session.commit()


def get_api_user_by_user_id(session: Session, user_id: int) -> GoogleApiUser | None:
    return session.query(GoogleApiUser).filter(GoogleApiUser.user_id == str(user_id)).first()


def delete_api_user(session: Session, user_id: int, commit: bool = True) -> None:
    session.query(GoogleCalendarSync).filter(GoogleCalendarSync.user_id == str(user_id)).delete()
    session.query(GoogleApiUser).filter(GoogleApiUser.user_id == str(user_id)).delete()
    if commit:
        session.commit()


def get_calendar_sync(
    session: Session, user_id: int, calendar_type: GoogleCalendarType
) -> GoogleCalendarSync | None:
    return (
        session.query(GoogleCalendarSync)
        .filter(
            GoogleCalendarSync.user_id == str(user_id),
            GoogleCalendarSync.calendar_type == calendar_type,
        )
        .first()
    )


def get_calendar_syncs(
    session: Session,
    calendar_type: GoogleCalendarType | None = None,
    setup_finished: bool | None = None,
) -> list[GoogleCalendarSync]:
    query = session.query(GoogleCalendarSync)
    if calendar_type is not None:
        query = query.filter(GoogleCalendarSync.calendar_type == calendar_type)
    if setup_finished is not None:
        query = query.filter(GoogleCalendarSync.setup_finished == setup_finished)
    return query.order_by(GoogleCalendarSync.id).all()


def add_calendar_sync(
    session: Session, user_id: int, calendar_type: GoogleCalendarType, commit: bool = True
) -> None:
    if get_calendar_sync(session, user_id, calendar_type) is None:
        session.add(GoogleCalendarSync(user_id=str(user_id), calendar_type=calendar_type))
    if commit:
        session.commit()


def delete_calendar_sync(
    session: Session, user_id: int, calendar_type: GoogleCalendarType, commit: bool = True
) -> bool:
    calendar_sync = get_calendar_sync(session, user_id, calendar_type)
    if calendar_sync is None:
        return False
    session.delete(calendar_sync)
    session.flush()
    if (
        session.query(GoogleCalendarSync).filter(GoogleCalendarSync.user_id == str(user_id)).first()
        is None
    ):
        session.query(GoogleApiUser).filter(GoogleApiUser.user_id == str(user_id)).delete()
    if commit:
        session.commit()
    return True


def set_calendar_sync_setup_finished(session: Session, sync_id: int, commit: bool = True) -> None:
    calendar_sync = session.get(GoogleCalendarSync, sync_id)
    if calendar_sync is not None:
        calendar_sync.setup_finished = True
    if commit:
        session.commit()


def get_calendar_id(
    session: Session, user_id: int, calendar_type: GoogleCalendarType
) -> str | None:
    calendar = (
        session.query(GoogleCalendar)
        .filter(
            GoogleCalendar.user_id == str(user_id), GoogleCalendar.calendar_type == calendar_type
        )
        .first()
    )
    return calendar.calendar_id if calendar else None


def set_calendar_id(
    session: Session,
    user_id: int,
    calendar_type: GoogleCalendarType,
    calendar_id: str,
    commit: bool = True,
) -> None:
    calendar = (
        session.query(GoogleCalendar)
        .filter(
            GoogleCalendar.user_id == str(user_id), GoogleCalendar.calendar_type == calendar_type
        )
        .first()
    )
    if calendar is None:
        session.add(
            GoogleCalendar(
                user_id=str(user_id), calendar_type=calendar_type, calendar_id=calendar_id
            )
        )
    else:
        calendar.calendar_id = calendar_id
    if commit:
        session.commit()
