from datetime import date, datetime
from enum import Enum

from sqlmodel import Field, SQLModel

from moobot.db.session import engine


class MoobloomEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    channel_name: str
    start_date: date | None
    start_time: datetime | None
    end_date: date | None
    end_time: datetime | None
    location: str | None
    description: str | None
    url: str | None
    image_url: str | None

    announcement_message_id: str | None


class MoobloomEventAttendanceType(str, Enum):
    ATTENDING = "attending"
    MAYBE = "maybe"
    NO = "no"


class MoobloomEventRSVP(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int
    event_id: int
    attendance_type: MoobloomEventAttendanceType


SQLModel.metadata.create_all(engine)
