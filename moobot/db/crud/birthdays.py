from sqlalchemy.orm import Session

from moobot.db.models import Birthday


def get_birthday(session: Session, user_id: int) -> Birthday | None:
    return session.query(Birthday).filter(Birthday.user_id == str(user_id)).first()


def get_birthdays(session: Session) -> list[Birthday]:
    return session.query(Birthday).order_by(Birthday.month, Birthday.day).all()


def set_birthday(session: Session, user_id: int, month: int, day: int, commit: bool = True) -> None:
    birthday = get_birthday(session, user_id)
    if birthday is None:
        session.add(Birthday(user_id=str(user_id), month=month, day=day))
    else:
        birthday.month = month
        birthday.day = day
    if commit:
        session.commit()


def delete_birthday(session: Session, user_id: int, commit: bool = True) -> bool:
    birthday = get_birthday(session, user_id)
    if birthday is None:
        return False
    session.delete(birthday)
    if commit:
        session.commit()
    return True
