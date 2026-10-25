from sqlalchemy.orm import Session

from moobot.db.models import GoogleApiAuthSession, GoogleApiUser, GoogleCalendar


def create_auth_session(
    session: Session, state: str, code_verifier: str, user_id: int, commit: bool = True
) -> None:
    session.add(
        GoogleApiAuthSession(
            state=state,
            code_verifier=code_verifier,
            user_id=str(user_id),
        )
    )
    if commit:
        session.commit()


def get_auth_session_by_state(session: Session, state: str) -> GoogleApiAuthSession | None:
    return session.query(GoogleApiAuthSession).filter(GoogleApiAuthSession.state == state).first()


def create_api_user(
    session: Session,
    user_id: int,
    token: str,
    refresh_token: str,
    token_uri: str,
    scopes: str,
    commit: bool = True,
) -> None:
    session.add(
        GoogleApiUser(
            user_id=str(user_id),
            token=token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            scopes=scopes,
        )
    )
    if commit:
        session.commit()


def get_api_user_by_user_id(session: Session, user_id: int) -> GoogleApiUser | None:
    return session.query(GoogleApiUser).filter(GoogleApiUser.user_id == str(user_id)).first()


def get_api_users_by_setup_finished(session: Session, setup_finished: bool) -> list[GoogleApiUser]:
    return session.query(GoogleApiUser).filter(GoogleApiUser.setup_finished == setup_finished).all()


def get_calendar_id(session: Session, user_id: int) -> str | None:
    calendar = session.query(GoogleCalendar).filter(GoogleCalendar.user_id == str(user_id)).first()
    return calendar.calendar_id if calendar else None


def set_calendar_id(session: Session, user_id: int, calendar_id: str, commit: bool = True) -> None:
    calendar = session.query(GoogleCalendar).filter(GoogleCalendar.user_id == str(user_id)).first()
    if calendar is None:
        session.add(GoogleCalendar(user_id=str(user_id), calendar_id=calendar_id))
    else:
        calendar.calendar_id = calendar_id
    if commit:
        session.commit()
