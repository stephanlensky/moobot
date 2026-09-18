from datetime import date, datetime
from zoneinfo import ZoneInfo

from moobot.settings import get_settings

settings = get_settings()


def local_tz() -> ZoneInfo:
    """The timezone the bot presents times in, as configured by the TZ setting."""
    return ZoneInfo(settings.tz)


def now() -> datetime:
    """
    The current local wall-clock time, without a tzinfo.

    Event times are stored and compared as naive local datetimes (the database columns are
    naive, and the configured timezone is sent to Google Calendar alongside the value), so
    this resolves "now" in the configured zone and then drops the tzinfo to match.
    """
    return datetime.now(local_tz()).replace(tzinfo=None)


def today() -> date:
    """Today's date in the configured timezone."""
    return datetime.now(local_tz()).date()
