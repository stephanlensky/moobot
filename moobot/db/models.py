from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from moobot.settings import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


class MoobloomEvent(Base):
    __tablename__ = "moobloomevent"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    create_channel: Mapped[bool] = mapped_column(default=True)
    channel_name: Mapped[Optional[str]]

    # event time fields
    # start_date and end_date must always be set
    # for single-day events, end_date == start_date
    # for events with a start time and without a set end time, end_time should be None
    start_date: Mapped[date]
    start_time: Mapped[Optional[datetime]]
    end_date: Mapped[date]
    end_time: Mapped[Optional[datetime]]

    location: Mapped[Optional[str]]
    description: Mapped[Optional[str]]
    url: Mapped[Optional[str]]
    image_url: Mapped[Optional[str]]
    thumbnail_url: Mapped[Optional[str]]

    announcement_message_id: Mapped[Optional[str]]
    channel_id: Mapped[Optional[str]]

    out_of_sync: Mapped[bool] = mapped_column(default=False)

    rsvps: Mapped[list["MoobloomEventRSVP"]] = relationship(back_populates="event")


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


class MoobloomEventRSVP(Base):
    __tablename__ = "moobloomeventrsvp"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str]
    event_id: Mapped[int] = mapped_column(ForeignKey("moobloomevent.id"))
    attendance_type: Mapped[MoobloomEventAttendanceType]

    event: Mapped[MoobloomEvent] = relationship(back_populates="rsvps")
