from datetime import date, datetime, timedelta

import pytest
from pytest_mock import MockerFixture

from moobot.discord.views.event_modal import (
    EventDescriptionAndURLs,
    EventTime,
    _parse_event_description,
    _parse_event_time,
)
from moobot.util.time import now as local_now
from moobot.util.time import today as local_today

SEPTEMBER_21 = datetime(year=local_now().year, month=9, day=21)  # noqa: DTZ001
SEPTEMBER_21_7PM = SEPTEMBER_21.replace(hour=19)
SEPTEMBER_21_10PM = SEPTEMBER_21.replace(hour=22)
SEPTEMBER_28 = SEPTEMBER_21.replace(day=28)
SEPTEMBER_28_10PM = SEPTEMBER_21_10PM.replace(day=28)

SOME_URL = "https://some-url"
SOME_OTHER_URL = "https://some-other-url"
SOME_OTHER_OTHER_URL = "https://some-other-other-url"
SOME_SHORT_DESCRIPTION = "Some description"
SOME_MULTILINE_DESCRIPTION = "Some\nmultiline\ndescription"


@pytest.mark.parametrize(
    "time_str,expected",
    [
        (
            "9/21",
            EventTime(
                start_date=SEPTEMBER_21.date(),
                start_time=None,
                end_date=SEPTEMBER_21.date(),
                end_time=None,
            ),
        ),
        (
            "9/21 7PM",
            EventTime(
                start_date=SEPTEMBER_21.date(),
                start_time=SEPTEMBER_21_7PM,
                end_date=SEPTEMBER_21.date(),
                end_time=None,
            ),
        ),
        (
            "Sept 21 7PM",
            EventTime(
                start_date=SEPTEMBER_21.date(),
                start_time=SEPTEMBER_21_7PM,
                end_date=SEPTEMBER_21.date(),
                end_time=None,
            ),
        ),
        (
            "9/21 7PM to 9/21 10PM",
            EventTime(
                start_date=SEPTEMBER_21.date(),
                start_time=SEPTEMBER_21_7PM,
                end_date=SEPTEMBER_21.date(),
                end_time=SEPTEMBER_21_10PM,
            ),
        ),
        (
            "9/21 7PM to 10PM",
            EventTime(
                start_date=SEPTEMBER_21.date(),
                start_time=SEPTEMBER_21_7PM,
                end_date=SEPTEMBER_21.date(),
                end_time=SEPTEMBER_21_10PM,
            ),
        ),
        (
            "9/21 to 9/28",
            EventTime(
                start_date=SEPTEMBER_21.date(),
                start_time=None,
                end_date=SEPTEMBER_28.date(),
                end_time=None,
            ),
        ),
        (
            "9/21 7PM to 9/28 10PM",
            EventTime(
                start_date=SEPTEMBER_21.date(),
                start_time=SEPTEMBER_21_7PM,
                end_date=SEPTEMBER_28.date(),
                end_time=SEPTEMBER_28_10PM,
            ),
        ),
    ],
)
def test__parse_event_time__various_time_strings__parses_correctly(
    time_str: str, expected: EventTime
) -> None:
    assert _parse_event_time(time_str) == expected


@pytest.mark.parametrize(
    "description_str,expected",
    [
        (
            "",
            EventDescriptionAndURLs(description=None, url=None, image_url=None),
        ),
        (
            f"{SOME_URL}\n{SOME_SHORT_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_SHORT_DESCRIPTION, url=SOME_URL, image_url=None
            ),
        ),
        (
            f"url:{SOME_URL}\n{SOME_SHORT_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_SHORT_DESCRIPTION, url=SOME_URL, image_url=None
            ),
        ),
        (
            f"{SOME_URL}\n{SOME_OTHER_URL}\n{SOME_SHORT_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_SHORT_DESCRIPTION, url=SOME_URL, image_url=SOME_OTHER_URL
            ),
        ),
        (
            f"url:{SOME_URL}\nimage_url:{SOME_OTHER_URL}\n{SOME_SHORT_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_SHORT_DESCRIPTION, url=SOME_URL, image_url=SOME_OTHER_URL
            ),
        ),
        (
            f"url:{SOME_URL}\nimage_url:{SOME_OTHER_URL}",
            EventDescriptionAndURLs(description=None, url=SOME_URL, image_url=SOME_OTHER_URL),
        ),
        (
            f"{SOME_URL}\n{SOME_MULTILINE_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_MULTILINE_DESCRIPTION, url=SOME_URL, image_url=None
            ),
        ),
        (
            f"image_url:{SOME_URL}\n{SOME_MULTILINE_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_MULTILINE_DESCRIPTION, url=None, image_url=SOME_URL
            ),
        ),
        (
            f"{SOME_MULTILINE_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_MULTILINE_DESCRIPTION, url=None, image_url=None
            ),
        ),
    ],
)
def test__parse_event_description__various_descriptions__parses_correctly(
    description_str: str, expected: EventDescriptionAndURLs
) -> None:
    assert _parse_event_description(description_str) == expected


# a fixed "now" so the year-inference tests don't depend on the day they're run. mid-year and
# mid-day, so that dates on either side of today are unambiguous.
FROZEN_NOW = datetime(year=2026, month=6, day=15, hour=12)  # noqa: DTZ001


@pytest.fixture
def frozen_now(mocker: MockerFixture) -> datetime:
    """Pin the event modal's notion of "now" to FROZEN_NOW."""
    mocker.patch("moobot.discord.views.event_modal.local_now", return_value=FROZEN_NOW)
    return FROZEN_NOW


@pytest.mark.parametrize(
    "time_str,expected",
    [
        # an event later today must stay today, not jump to next year. a date with no time parses
        # to midnight, which is already in the past by the time anyone creates the event.
        (
            "6/15",
            EventTime(
                start_date=date(2026, 6, 15),
                start_time=None,
                end_date=date(2026, 6, 15),
                end_time=None,
            ),
        ),
        (
            "June 15",
            EventTime(
                start_date=date(2026, 6, 15),
                start_time=None,
                end_date=date(2026, 6, 15),
                end_time=None,
            ),
        ),
        # an explicit year is never second-guessed, even when it's in the past
        (
            "2026-06-15",
            EventTime(
                start_date=date(2026, 6, 15),
                start_time=None,
                end_date=date(2026, 6, 15),
                end_time=None,
            ),
        ),
        (
            "2025-06-15",
            EventTime(
                start_date=date(2025, 6, 15),
                start_time=None,
                end_date=date(2025, 6, 15),
                end_time=None,
            ),
        ),
        # a range starting today keeps both ends in the same year
        (
            "6/15 to 6/21",
            EventTime(
                start_date=date(2026, 6, 15),
                start_time=None,
                end_date=date(2026, 6, 21),
                end_time=None,
            ),
        ),
        # a genuinely past date is still bumped to next year, along with the rest of the range
        (
            "6/14",
            EventTime(
                start_date=date(2027, 6, 14),
                start_time=None,
                end_date=date(2027, 6, 14),
                end_time=None,
            ),
        ),
        (
            "6/14 to 6/20",
            EventTime(
                start_date=date(2027, 6, 14),
                start_time=None,
                end_date=date(2027, 6, 20),
                end_time=None,
            ),
        ),
        # a range that wraps the new year still ends after it starts
        (
            "12/31 to 1/1",
            EventTime(
                start_date=date(2026, 12, 31),
                start_time=None,
                end_date=date(2027, 1, 1),
                end_time=None,
            ),
        ),
    ],
)
def test__parse_event_time__year_inference__does_not_shift_current_events(
    frozen_now: datetime, time_str: str, expected: EventTime
) -> None:
    assert _parse_event_time(time_str) == expected


def test__parse_event_time__start_after_end__raises(frozen_now: datetime) -> None:
    with pytest.raises(ValueError, match="is after end date"):
        _parse_event_time("2026-06-20 to 2026-06-15")


def test__parse_event_time__range_ending_on_weekday__uses_that_weekday() -> None:
    """
    A weekday name carries a date of its own, so it must not be collapsed onto the start date the
    way a bare time like "10PM" is. dateutil resolves it against the real current date, so this is
    asserted relative to today rather than against a frozen clock.
    """
    today = local_today()
    # the coming Sunday, which is today when today is already a Sunday
    next_sunday = today + timedelta(days=(6 - today.weekday()) % 7)

    parsed = _parse_event_time(f"{today.month}/{today.day} to Sunday")

    assert parsed.start_date == today
    assert parsed.end_date == next_sunday
