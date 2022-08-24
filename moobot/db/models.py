from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import root_validator
from sqlmodel import Field, SQLModel

from moobot.db.session import engine
from moobot.settings import get_settings

settings = get_settings()


class MoobloomEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    channel_name: str
    start_date: date
    start_time: datetime | None
    end_date: date
    end_time: datetime | None
    location: str | None
    description: str | None
    url: str | None
    image_url: str | None

    announcement_message_id: str | None
    channel_id: str | None

    @root_validator(pre=True)
    @classmethod
    def validate_and_fix_date_fields(cls, values: dict[str, Any]) -> dict[str, Any]:
        if "start_time" in values and "start_date" in values:
            raise ValueError("start_date and start_time cannot both be specified")
        if "end_time" in values and "end_date" in values:
            raise ValueError("end_date and end_time cannot both be specified")

        start_time: Optional[datetime] = values.get("start_time")
        if start_time and isinstance(start_time, datetime):
            values["start_date"] = start_time.date()
        end_time: Optional[datetime] = values.get("end_time")
        if end_time and isinstance(end_time, datetime):
            values["end_date"] = end_time.date()

        if "end_date" not in values:
            values["end_date"] = values["start_date"]

        return values


class MoobloomEventAttendanceType(str, Enum):
    YES = "attending"
    MAYBE = "maybe"
    NO = "no"

    @classmethod
    def from_rsvp_react_emoji(cls, emoji: str) -> MoobloomEventAttendanceType:
        if emoji == settings.rsvp_yes_emoji:
            return MoobloomEventAttendanceType.YES
        if emoji == settings.rsvp_maybe_emoji:
            return MoobloomEventAttendanceType.MAYBE
        if emoji == settings.rsvp_no_emoji:
            return MoobloomEventAttendanceType.NO
        raise NotImplementedError(emoji)

    @property
    def rsvp_react_emoji(self) -> str:
        if self == MoobloomEventAttendanceType.YES:
            return settings.rsvp_yes_emoji
        if self == MoobloomEventAttendanceType.MAYBE:
            return settings.rsvp_maybe_emoji
        if self == MoobloomEventAttendanceType.NO:
            return settings.rsvp_no_emoji
        raise NotImplementedError(self)


class MoobloomEventRSVP(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str
    event_id: int
    attendance_type: MoobloomEventAttendanceType


SQLModel.metadata.create_all(engine)
