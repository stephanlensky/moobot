def mention(user_id: str) -> str:
    return f"<@{user_id}>"


def channel_mention(channel_id: str) -> str:
    return f"<#{channel_id}>"
