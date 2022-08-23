import calendar
from datetime import date, datetime


def format_event_duration(
    start_date: date | None,
    start_time: datetime | None,
    end_date: date | None,
    end_time: datetime | None,
) -> str:
    if start_time and end_time and start_time.day == end_time.day:
        stime = start_time.strftime("%-I:%M %p")
        etime = end_time.strftime("%-I:%M %p")
        return f"{calendar.month_name[start_time.month]} {start_time.day} {stime}-{etime}"
    elif start_time and end_time:
        stime = start_time.strftime("%-I:%M %p")
        etime = end_time.strftime("%-I:%M %p")
        return (
            f"{calendar.month_name[start_time.month]} {start_time.day} {stime} to"
            f" {calendar.month_name[end_time.month]} {end_time.day} {etime}"
        )
    elif start_date and end_date:
        return (
            f"{calendar.month_name[start_date.month]} {start_date.day} to"
            f" {calendar.month_name[end_date.month]} {end_date.day}"
        )
    elif start_time:
        stime = start_time.strftime("%-I:%M %p")
        return f"{calendar.month_name[start_time.month]} {start_time.day} {stime}"
    elif start_date:
        return f"{calendar.month_name[start_date.month]} {start_date.day}"

    raise ValueError(f"can't format dates {start_date=} {start_time=} {end_date=} {end_time=}")
