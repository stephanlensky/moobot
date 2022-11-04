from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import root_validator, validator
from sqlmodel import Field, Relationship, SQLModel

from moobot.db.session import engine
from moobot.settings import get_settings

settings = get_settings()


class MoobloomEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    create_channel: bool = True
    channel_name: str | None

    # event time fields
    # start_date and end_date must always be set
    # for single-day events, end_date == start_date
    # for events with a start time and without a set end time, end_time should be None
    start_date: date
    start_time: datetime | None
    end_date: date
    end_time: datetime | None

    location: str | None
    description: str | None
    url: str | None
    image_url: str | None
    thumbnail_url: str | None

    announcement_message_id: str | None
    channel_id: str | None

    out_of_sync: bool = False

    rsvps: list["MoobloomEventRSVP"] = Relationship(back_populates="event")

    @root_validator(pre=True)
    def validate_and_fix_date_fields(cls, values: dict[str, Any]) -> dict[str, Any]:
        start_time: Optional[datetime] = values.get("start_time")
        if start_time and isinstance(start_time, datetime):
            values["start_date"] = start_time.date()

        end_time: Optional[datetime] = values.get("end_time")
        if end_time and isinstance(end_time, datetime):
            values["end_date"] = end_time.date()

        if "end_date" not in values:
            values["end_date"] = values["start_date"]

        return values

    @root_validator(pre=True)
    def validate_create_channel(cls, values: dict[str, Any]) -> dict[str, Any]:
        if values.get("channel_name") and values.get("create_channel") == False:
            raise ValueError("If create_channel is false, channel name should not be provided")
        if values.get("channel_name"):
            values["create_channel"] = True
        elif values.get("create_channel"):
            raise ValueError("channel_name must be provided")

        return values

    @validator("channel_name")
    def remove_pound_symbol_from_channel_name(cls, v: str | None) -> str | None:
        return v.removeprefix("#") if v else v


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
    event_id: int = Field(foreign_key="moobloomevent.id")
    attendance_type: MoobloomEventAttendanceType

    event: MoobloomEvent = Relationship(back_populates="rsvps")


SQLModel.metadata.create_all(engine)
