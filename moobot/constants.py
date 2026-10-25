from datetime import timedelta

GOOGLE_CALENDAR_SYNC_ENABLE_DM_TEMPLATE = (
    "**Mooooo!** :cow:\n\nTo finish setting up Google Calendar sync,"
    " [authorize access to your Google account]({auth_url}).\n\nAfter authorizing access, your"
    " RSVPs will be automatically synced to your Google Calendar."
)
GOOGLE_CALENDAR_SYNC_ENABLE_USER_EXISTS_DM = (
    "Hm... you added a reaction to enable Google Calendar syncing, but sync was already enabled! I"
    " won't do anything. To disable syncing, remove your reaction."
)
GOOGLE_CALENDAR_SYNC_DISABLE_DM = "Google Calendar sync has been successfully disabled."
GOOGLE_CALENDAR_SYNC_SETUP_COMPLETE_DM = "Google calendar sync has been set up successfully."
GOOGLE_CALENDAR_SYNC_TOKEN_NOT_AUTHORIZED = (
    "Hi {name}, I just tried syncing your RSVPs to Google Calendar, but it seems like Moobot's"
    " authorization to your Google account has either expired or been revoked.\n\nIf you would like"
    " to continue syncing to Google Calendar, please reauthorize Moobot by removing and readding"
    " your Google Calendar reaction on the calendar page."
)

DISCORD_MESSAGE_LENGTH_LIMIT = 2000
AGENT_CONTEXT_MESSAGE_LIMIT = 15
AGENT_CONTEXT_MAX_AGE = timedelta(hours=24)
AGENT_TURN_FAILED_MESSAGE = "Sorry {mention}! Something went wrong while I was working on that."
AGENT_CONVERSATION_CLEARED_MESSAGE = "Okay, I've cleared our conversation in this channel."
AGENT_NO_CONVERSATION_MESSAGE = "There's no conversation to clear in this channel."
