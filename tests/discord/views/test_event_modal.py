from datetime import datetime

import pytest

from moobot.discord.views.event_modal import (
    EventDescriptionAndURLs,
    EventTime,
    _parse_event_description,
    _parse_event_time,
)

SEPTEMBER_21 = datetime(year=datetime.now().year, month=9, day=21)
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
            f"{SOME_URL} {SOME_SHORT_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_SHORT_DESCRIPTION, url=SOME_URL, image_url=None
            ),
        ),
        (
            f"url:{SOME_URL} {SOME_SHORT_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_SHORT_DESCRIPTION, url=SOME_URL, image_url=None
            ),
        ),
        (
            f"{SOME_URL} {SOME_OTHER_URL} {SOME_SHORT_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_SHORT_DESCRIPTION, url=SOME_URL, image_url=SOME_OTHER_URL
            ),
        ),
        (
            f"url:{SOME_URL} image_url:{SOME_OTHER_URL} {SOME_SHORT_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_SHORT_DESCRIPTION, url=SOME_URL, image_url=SOME_OTHER_URL
            ),
        ),
        (
            f"{SOME_URL} {SOME_MULTILINE_DESCRIPTION}",
            EventDescriptionAndURLs(
                description=SOME_MULTILINE_DESCRIPTION, url=SOME_URL, image_url=None
            ),
        ),
        (
            f"image_url:{SOME_URL} {SOME_MULTILINE_DESCRIPTION}",
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
