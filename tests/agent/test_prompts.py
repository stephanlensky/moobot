from datetime import UTC, datetime

from pytest_mock import MockerFixture

from moobot.agent.prompts import ChannelMessage, get_instructions, get_turn_input


def test_get_instructions__includes_current_time_and_timezone(mocker: MockerFixture) -> None:
    now = datetime(2026, 10, 25, 14, 30)  # noqa: DTZ001
    mocker.patch("moobot.agent.prompts.local_now", return_value=now)

    instructions = get_instructions()

    assert "Sun. October 25, 2026 2:30 PM (America/New_York)" in instructions


def test_get_turn_input__no_channel_messages__only_includes_message() -> None:
    turn_input = get_turn_input([], "Alice", 123, "when is the hayride?")

    assert turn_input == (
        "Message to reply to, from Alice (<@123>):\n<message>\nwhen is the hayride?\n</message>"
    )


def test_get_turn_input__channel_messages__includes_context_before_message() -> None:
    channel_messages = [
        ChannelMessage("Bob", datetime(2026, 10, 25, 18, 1, tzinfo=UTC), "hayride anyone?"),
        ChannelMessage("Carol", datetime(2026, 10, 25, 18, 3, tzinfo=UTC), "maybe!"),
    ]

    turn_input = get_turn_input(channel_messages, "Alice", 123, "when is the hayride?")

    assert turn_input == (
        "Earlier messages in this channel, oldest first (context only):\n"
        "<channel_context>\n"
        "[Sun. October 25, 2026 2:01 PM] Bob: hayride anyone?\n"
        "[Sun. October 25, 2026 2:03 PM] Carol: maybe!\n"
        "</channel_context>\n"
        "\n"
        "Message to reply to, from Alice (<@123>):\n"
        "<message>\nwhen is the hayride?\n</message>"
    )
