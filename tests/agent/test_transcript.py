from agents import TResponseInputItem

from moobot.agent.transcript import get_transcript_start_index, is_user_message


def _get_turn_items(index: int) -> list[TResponseInputItem]:
    return [
        {"role": "user", "content": f"question {index}"},
        {
            "type": "reasoning",
            "id": f"rs_{index}",
            "summary": [{"type": "summary_text", "text": "look it up"}],
        },
        {
            "type": "function_call",
            "call_id": f"call_{index}",
            "name": "get_events",
            "arguments": "{}",
        },
        {"type": "function_call_output", "call_id": f"call_{index}", "output": "[]"},
        {
            "type": "message",
            "id": f"msg_{index}",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": f"answer {index}", "annotations": []}],
        },
    ]


def _get_transcript(turn_count: int) -> list[TResponseInputItem]:
    return [item for index in range(turn_count) for item in _get_turn_items(index)]


def test_is_user_message__detects_only_user_messages() -> None:
    items = _get_turn_items(0)

    assert [is_user_message(item) for item in items] == [True, False, False, False, False]
    assert is_user_message({"type": "message", "role": "user", "content": "hi"})


def test_get_transcript_start_index__within_limit__keeps_everything() -> None:
    assert get_transcript_start_index(_get_transcript(3), turn_limit=3) == 0
    assert get_transcript_start_index([], turn_limit=3) == 0


def test_get_transcript_start_index__over_limit__starts_at_user_message() -> None:
    transcript = _get_transcript(5)

    start_index = get_transcript_start_index(transcript, turn_limit=2)

    assert start_index == 15
    assert transcript[start_index:] == [*_get_turn_items(3), *_get_turn_items(4)]


def test_get_transcript_start_index__keeps_tool_calls_with_outputs() -> None:
    transcript = _get_transcript(4)

    trimmed = transcript[get_transcript_start_index(transcript, turn_limit=3) :]

    call_ids = [item.get("call_id") for item in trimmed if item.get("type") == "function_call"]
    output_call_ids = [
        item.get("call_id") for item in trimmed if item.get("type") == "function_call_output"
    ]
    assert call_ids == output_call_ids == ["call_1", "call_2", "call_3"]
    assert is_user_message(trimmed[0])
