from dataclasses import dataclass
from datetime import datetime

from dateutil import parser


@dataclass
class TimeAwareParserResult:
    dt: datetime
    has_time: bool
    has_date: bool
    has_year: bool


class TimeAwareParser(parser.parser):
    def _build_naive(self, res, default):  # type: ignore
        naive = super()._build_naive(res, default)
        return TimeAwareParserResult(
            dt=naive,
            has_time=res.hour is not None,
            # a weekday name like "Sunday" resolves to a real date even though no day-of-month
            # was given, so it counts as specifying a date
            has_date=res.day is not None or res.weekday is not None,
            has_year=res.year is not None,
        )


time_aware_parser = TimeAwareParser()
