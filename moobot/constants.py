from datetime import timedelta

from discord import AllowedMentions

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
AGENT_TRANSCRIPT_TURN_LIMIT = 30
AGENT_TURN_FAILED_MESSAGE = "Sorry {mention}! Something went wrong while I was working on that."
AGENT_EMPTY_OUTPUT_MESSAGE = "moo?? i forgot what i was gonna say"
AGENT_CONVERSATION_CLEARED_MESSAGE = "Okay, I've cleared our conversation in this channel."
AGENT_NO_CONVERSATION_MESSAGE = "There's no conversation to clear in this channel."
AGENT_ACTION_VIEW_TIMEOUT = timedelta(minutes=15)
AGENT_BUTTON_ATTEMPT_TTL = timedelta(hours=1)
AGENT_BUTTON_EASTER_EGG_ATTEMPTS = 30
AGENT_NOT_YOUR_BUTTON_MESSAGES: list[tuple[int, list[str]]] = [
    (
        1,
        [
            "not ur button bozo",
            "hands off moo",
            "moo hey thats not ur button. ask me urself if u want one",
            "nope. not urs moo",
        ],
    ),
    (
        3,
        [
            "still not ur button",
            "moo. MOO. not yours",
            "u can keep clicking but its still not ur button",
            "mooo stop thats somebody elses",
        ],
    ),
    (
        6,
        [
            "this isnt ur button, are u stupid?",
            "do u know how to read?",
            "moo im begging u. NOT. YOURS.",
            "even the chickens know this isnt ur button",
        ],
    ),
    (
        11,
        [
            "im telling the farmer",
            "every click makes me lose a stomach",
            "moo ok ur actually scaring the herd now",
            "i have 4 stomachs and all of them are disappointed in u",
            "the farmer has been notified. hes coming. moo",
        ],
    ),
    (
        21,
        [
            "ok at this point i respect the commitment. still no",
            "uve clicked this more times than ive been milked today",
            "moo... do u not have grass to eat or smth",
            "this is genuinely impressive. still not ur button tho",
            "i would simply stop. but u wont. moo",
        ],
    ),
]
AGENT_ACTION_ALREADY_USED_MESSAGE = "mooo that button already got used"
AGENT_REPLY_ALLOWED_MENTIONS = AllowedMentions(
    everyone=False, roles=False, users=True, replied_user=True
)
AGENT_TRANSCRIPT_NOTE_PREFIX = "[Event form update, not a message]"
AGENT_EVENT_CREATED_MESSAGES = [
    "ok {name} is on the calendar moo. dont be late",
    "mooo {name} is official now. its on teh calendar",
    "{mention} added {name} moo. ok im kinda excited ngl",
    "done moo {name} is in. MOOO",
    "{name} is happening!! its on the calendar now mooooo",
    "fine. {name} is on the calendar. happy now? moo",
    "added {name}. i expect snacks moo",
    "ok {name} exists now. u owe me grass moo",
    "{name} is in moo\nwait theres a fly\nok anyway its on the calendar",
    "mooo {name} is on teh calendar\n*the",
    "ugh fine its done. {name}. moooooooo",
    "{mention} made {name} happen moo. dont make me regret this",
]
AGENT_EVENT_UPDATED_MESSAGES = [
    "ok updated {name} moo. its all fxied",
    "mooo {name} got changed. check the calendar",
    "{mention} updated {name} moo. calendar is all up to date",
    "done. {name} is updated m o o",
    "ok {name} is sorted now moo... i think. yea it is",
    "updated {name}. AGAIN. moo",
    "fine. {name} is changed. make up ur mind next time moo",
    "ok {name} is updated. pls stop moving it around moooo",
    "{name} is fixed now moo\nhopefully for the last time",
    "{mention} changed {name} moo. i was napping but ok",
    "sigh. {name} updated. moo",
    "mooo ok {name} is diffrent now\n*different",
]
AGENT_EVENT_DELETED_MESSAGES = [
    "ok {name} is gone moo. rip",
    "mooo deleted {name}. its off the calendar",
    "{mention} deleted {name} moo. sad but ok",
    "{name} is no more. MOO",
    "done moo {name} got deleted. nooooo",
    "{name} is gone. i was gonna go to that moo",
    "deleted {name}. hope ur happy {mention} moo",
    "ok {name} is off the calendar. one less thing moo",
    "moo... {name} is gone\ngonna go stare at a fence for a bit",
    "{name} has left the pasture. moooooo",
    "fine. {name} deleted. dont come crying to me moo",
]
AGENT_EVENT_DELETE_CANCELLED_MESSAGES = [
    "ok not deleting {name} moo. it lives",
    "phew moo {name} stays on the calendar",
    "{mention} changed their mind. {name} is safe moo",
    "mooo ok {name} is staying. good",
    "nvm then. {name} isnt going anywhere moo",
    "so u made me get up for nothing. {name} stays moo",
    "ok {name} survives. make up ur mind moo",
    "cancelled. {name} is still on. moooo",
    "wow ok {name} lives\nthat was a waste of a moo",
    "fine {name} stays. i didnt want to delete it anyway moo",
]
