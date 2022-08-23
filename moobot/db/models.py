from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlmodel import Field, SQLModel

from moobot.db.session import engine
from moobot.settings import get_settings

settings = get_settings()


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
    channel_id: str | None

    @property
    def __start_date(self) -> date:
        if self.start_time:
            return self.start_time
        elif self.start_date:
            return self.start_date
        raise ValueError("start time/date not specified")

    @property
    def __end_date(self) -> date:
        if self.end_time:
            return self.end_time
        elif self.end_date:
            return self.end_date
        raise ValueError("end time/date not specified")

    @property
    def start_day(self) -> int:
        return self.__start_date.day

    @property
    def start_month(self) -> int:
        return self.__start_date.month

    @property
    def start_year(self) -> int:
        return self.__start_date.year

    @property
    def end_day(self) -> int:
        return self.__end_date.day

    @property
    def end_month(self) -> int:
        return self.__end_date.month

    @property
    def end_year(self) -> int:
        return self.__end_date.year

    def has_end_date(self) -> bool:
        return self.end_date is not None or self.end_time is not None


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
