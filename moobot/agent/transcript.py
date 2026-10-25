from agents import TResponseInputItem

from moobot.constants import AGENT_TRANSCRIPT_TURN_LIMIT


def is_user_message(item: TResponseInputItem) -> bool:
    return item.get("role") == "user" and item.get("type", "message") == "message"


def get_transcript_start_index(
    transcript: list[TResponseInputItem], turn_limit: int = AGENT_TRANSCRIPT_TURN_LIMIT
) -> int:
    user_message_indexes = [index for index, item in enumerate(transcript) if is_user_message(item)]
    if len(user_message_indexes) <= turn_limit:
        return 0
    return user_message_indexes[-turn_limit]
