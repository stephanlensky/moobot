import calendar
from datetime import date, datetime


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
        return f"{calendar.month_name[start_time.month]} {start_time.day} {stime}-{etime}"

    # event with a start and end time on different days
    if start_time and end_time:
        stime = start_time.strftime("%-I:%M %p")
        etime = end_time.strftime("%-I:%M %p")
        return (
            f"{calendar.month_name[start_time.month]} {start_time.day} {stime} to"
            f" {calendar.month_name[end_time.month]} {end_time.day} {etime}"
        )

    # single day event with a start time and no specified end time
    if start_time and not end_time:
        stime = start_time.strftime("%-I:%M %p")
        return f"{calendar.month_name[start_time.month]} {start_time.day} {stime}"

    # multi-day event
    if start_date != end_date:
        return (
            f"{calendar.month_name[start_date.month]} {start_date.day} to"
            f" {calendar.month_name[end_date.month]} {end_date.day}"
        )

    # single day event with no time specifieid
    if start_date:
        return f"{calendar.month_name[start_date.month]} {start_date.day}"

    raise ValueError(f"can't format dates {start_date=} {start_time=} {end_date=} {end_time=}")
