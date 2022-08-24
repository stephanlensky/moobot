import json
from datetime import date, datetime
from typing import Any, Callable

from dateutil import parser


def prompt(
    prompt_str: str, validator: Callable[[str], Any] | None = None, allow_none: bool = False
) -> Any:
    while True:
        answer: Any = input(prompt_str)
        if not allow_none and len(answer) == 0:
            print("Please enter a value")
        elif allow_none and len(answer) == 0:
            answer = None
            break
        elif validator:
            try:
                answer = validator(answer)
                break
            except Exception:
                print("Invalid answer")
        else:
            break

    return answer


def date_validator(answer: str) -> date:
    return parser.parse(answer).date()


def time_validator(answer: str) -> datetime:
    return parser.parse(answer)


print("Create a new Moobloom Event")
event_name: str = prompt("Event name: ")
channel_name: str = prompt("Channel name: ")
description: str = prompt("Description: ", allow_none=True)
start_date: date | None = prompt("Start date: ", date_validator)
start_time: datetime | None = prompt("Start time: ", time_validator, allow_none=True)
if start_time:
    start_time = start_time.replace(year=start_date.year, month=start_date.month, day=start_date.day)  # type: ignore
    start_date = None
end_date: date | None = prompt("End date: ", date_validator, allow_none=True)
end_time: datetime | None = None
if end_date:
    end_time = prompt("End time: ", time_validator, allow_none=True)
    if end_time:
        end_time = end_time.replace(year=end_date.year, month=end_date.month, day=end_date.day)
        end_date = None

location: str = prompt("Location: ", allow_none=True)
url: str = prompt("URL: ", allow_none=True)
thumbnail_url: str = prompt("Thumbnail URL: ", allow_none=True)
image_url: str = prompt("Image URL: ", allow_none=True)


event_json = {
    "name": event_name,
    "channel_name": channel_name,
    "start_date": start_date.isoformat() if start_date else None,
    "start_time": start_time.isoformat() if start_time else None,
    "end_date": end_date.isoformat() if end_date else None,
    "end_time": end_time.isoformat() if end_time else None,
    "location": location,
    "description": description,
    "thumbnail_url": thumbnail_url,
    "image_url": image_url,
    "url": url,
}
event_json = {k: v for k, v in event_json.items() if v is not None}
print(json.dumps(event_json))
