import calendar
from datetime import date, datetime

from moobot.db.models import MoobloomEvent


def format_event_duration(
    start_date: date,
    start_time: datetime | None,
    end_date: date,
    end_time: datetime | None,
) -> str:

    # event that has a start and end time on the same day
    if start_time and end_time and start_date == end_date:
        stime = start_time.strftime("%-I:%M %p")
        etime = end_time.strftime("%-I:%M %p")
        return (
            f"{start_time.strftime('%a')}."
            f" {calendar.month_name[start_time.month]} {start_time.day} {stime}-{etime}"
        )

    # event with a start and end time on different days
    if start_time and end_time:
        stime = start_time.strftime("%-I:%M %p")
        etime = end_time.strftime("%-I:%M %p")
        return (
            f"{start_time.strftime('%a')}."
            f" {calendar.month_name[start_time.month]} {start_time.day} {stime} to{end_time.strftime('%a')}."
            f"  {calendar.month_name[end_time.month]} {end_time.day} {etime}"
        )

    # single day event with a start time and no specified end time
    if start_time and not end_time:
        stime = start_time.strftime("%-I:%M %p")
        return (
            f"{start_time.strftime('%a')}."
            f" {calendar.month_name[start_time.month]} {start_time.day} {stime}"
        )

    # multi-day event
    if start_date != end_date:
        return (
            f"{start_date.strftime('%a')}."
            f" {calendar.month_name[start_date.month]} {start_date.day} to"
            f" {end_date.strftime('%a')}.  {calendar.month_name[end_date.month]} {end_date.day}"
        )

    # single day event with no time specified
    if start_date:
        return (
            f"{start_date.strftime('%a')}. {calendar.month_name[start_date.month]} {start_date.day}"
        )

    raise ValueError(f"can't format dates {start_date=} {start_time=} {end_date=} {end_time=}")


def format_event_duration_for_calendar(
    start_date: date,
    start_time: datetime | None,
    end_date: date,
    end_time: datetime | None,
) -> str:
    if start_time and start_time.minute == 0:
        stime = start_time.strftime("%-I")
    elif start_time:
        stime = start_time.strftime("%-I:%M")

    if end_time and end_time.minute == 0:
        etime = end_time.strftime("%-I")
    elif end_time:
        etime = end_time.strftime("%-I:%M")

    if start_time and end_time and start_time.strftime("%p") == end_time.strftime("%p"):
        tduration = start_time.strftime(f"{stime}-{etime} %p")
    elif start_time and end_time:
        tduration = f"{start_time.strftime(f'{stime} %p')}-{end_time.strftime(f'{etime} %p')}"

    # event that has a start and end time on the same day
    if start_time and end_time and start_date == end_date:
        return (
            f"{start_time.strftime('%a')}."
            f" {calendar.month_name[start_time.month]} {start_time.day}, {tduration}"
        )

    # event with a start and end time on different days
    if start_time and end_time:
        return (
            f"{start_time.strftime('%a')}."
            f" {calendar.month_name[start_time.month]} {start_time.day} {stime} to"
            f" {end_time.strftime('%a')}."
            f" {calendar.month_name[end_time.month]} {end_time.day} {etime}"
        )

    # single day event with a start time and no specified end time
    if start_time and not end_time:
        return (
            f"{start_time.strftime('%a')}."
            f" {calendar.month_name[start_time.month]} {start_time.day},"
            f" {start_time.strftime(f'{stime} %p')}"
        )

    # multi-day event
    if start_date != end_date:
        return (
            f"{start_date.strftime('%a')}."
            f" {calendar.month_name[start_date.month]} {start_date.day}-{end_date.strftime('%a')}."
            f" {calendar.month_name[end_date.month]} {end_date.day}"
        )

    # single day event with no time specified
    if start_date:
        return (
            f"{start_date.strftime('%a')}. {calendar.month_name[start_date.month]} {start_date.day}"
        )

    raise ValueError(f"can't format dates {start_date=} {start_time=} {end_date=} {end_time=}")


def format_single_event_for_calendar(event: MoobloomEvent) -> str:
    formatted_duration = format_event_duration_for_calendar(
        event.start_date, event.start_time, event.end_date, event.end_time
    )
    if event.start_date == date.today():
        return f"**📢  (Today!) {formatted_duration}: {event.name}**"
    if (
        event.start_date != event.end_date
        and date.today() >= event.start_date
        and date.today() <= event.end_date
    ):
        return f"**📢  (Ongoing) {formatted_duration}: {event.name}**"
    return f"{formatted_duration}: {event.name}"
