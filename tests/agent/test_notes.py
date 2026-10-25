from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from moobot.agent.notes import get_delete_cancelled_note, get_event_channel, get_event_note
from moobot.db.models import MoobloomEvent

PREFIX = "[Event form update, not a message]"


def _get_user() -> MagicMock:
    user = MagicMock(id=42, display_name="Stephan")
    user.name = ".stephan"
    return user


@pytest.mark.parametrize(
    "channel_id,channel_name,channel",
    [("555", "game-night", "<#555>"), (None, "game-night", "#game-night"), (None, None, "none")],
)
def test_get_event_channel__prefers_channel_then_name(
    channel_id: str | None, channel_name: str | None, channel: str
) -> None:
    event = MoobloomEvent(channel_id=channel_id, channel_name=channel_name)

    assert get_event_channel(event) == channel


@pytest.mark.parametrize("action", ["created", "updated", "deleted"])
def test_get_event_note__includes_author_id_and_saved_details(action: str) -> None:
    event = MoobloomEvent(
        id=12,
        name="Game Night",
        channel_name="game-night",
        start_date=date(2026, 10, 25),
        start_time=datetime(2026, 10, 25, 18),  # noqa: DTZ001
        end_date=date(2026, 10, 25),
        location="",
        description="Bring snacks\nand games",
        url="https://example.com/game-night",
    )

    assert get_event_note(_get_user(), action, event) == (
        f'{PREFIX} Stephan (@.stephan, <@42>) {action} the event "Game Night" (id 12):'
        " Sun. October 25 6:00 PM, location: none, channel: #game-night,"
        " url: https://example.com/game-night, description: Bring snacks\nand games"
    )


def test_get_delete_cancelled_note__includes_author_and_id() -> None:
    assert get_delete_cancelled_note(_get_user(), 12, "Game Night") == (
        f"{PREFIX} Stephan (@.stephan, <@42>) clicked Cancel instead of deleting the event"
        ' "Game Night" (id 12), so it was not deleted.'
    )
