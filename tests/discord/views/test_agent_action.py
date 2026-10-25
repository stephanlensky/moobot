import asyncio
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session, sessionmaker

from moobot.constants import (
    AGENT_ACTION_ALREADY_USED_MESSAGE,
    AGENT_EVENT_CREATED_MESSAGES,
    AGENT_EVENT_DELETE_CANCELLED_MESSAGES,
    AGENT_EVENT_DELETED_MESSAGES,
    AGENT_EVENT_UPDATED_MESSAGES,
    AGENT_NOT_YOUR_BUTTON_MESSAGES,
    AGENT_REPLY_ALLOWED_MENTIONS,
)
from moobot.db.models import MoobloomEvent
from moobot.discord.commands.update_event import UpdateEventError
from moobot.discord.views.agent_action import (
    AgentActionView,
    ButtonAttemptCounter,
    CreateEventView,
    DeleteEventView,
    EventFields,
    UpdateEventView,
    get_not_your_button_message,
)
from moobot.discord.views.event_modal import CreateEventModal, EventTime

AUTHOR_ID = 42
OTHER_USER_ID = 7
CHANNEL_ID = 1234
NOTE_PREFIX = "[Event form update, not a message]"
SEPTEMBER_21_TIME = EventTime(
    start_date=date(2026, 9, 21),
    start_time=datetime(2026, 9, 21, 19),  # noqa: DTZ001
    end_date=date(2026, 9, 21),
    end_time=datetime(2026, 9, 21, 22),  # noqa: DTZ001
)


@pytest.fixture(autouse=True)
def counter(mocker: MockerFixture) -> ButtonAttemptCounter:
    counter = ButtonAttemptCounter()
    mocker.patch("moobot.discord.views.agent_action.button_attempt_counter", counter)
    return counter


@pytest.fixture
def session(test_db_session: sessionmaker[Session], mocker: MockerFixture) -> sessionmaker[Session]:
    mocker.patch("moobot.discord.views.agent_action.Session", test_db_session)
    mocker.patch("moobot.discord.commands.update_event.Session", test_db_session)
    mocker.patch("moobot.discord.commands.update_event.initialize_events", AsyncMock())
    mocker.patch("moobot.discord.commands.create_event.Session", test_db_session)
    mocker.patch("moobot.discord.commands.create_event.initialize_events", AsyncMock())
    return test_db_session


def _get_bot() -> MagicMock:
    bot = MagicMock()
    bot.affirm.return_value = "Okay"
    bot.agent_worker.add_transcript_note = AsyncMock()
    return bot


def _get_original_message() -> MagicMock:
    message = MagicMock()
    message.id = 1
    message.channel.id = CHANNEL_ID
    message.reply = AsyncMock()
    return message


def _get_interaction(user_id: int = AUTHOR_ID) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.user.mention = f"<@{user_id}>"
    interaction.user.display_name = f"User {user_id}"
    interaction.user.name = f"user{user_id}"
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _get_author(user_id: int) -> str:
    return f"User {user_id} (@user{user_id}, <@{user_id}>)"


def _get_confirmations(phrases: list[str], name: str, user_id: int) -> list[str]:
    return [phrase.format(name=name, mention=f"<@{user_id}>") for phrase in phrases]


def _assert_confirmation_reply(
    original_message: MagicMock, phrases: list[str], name: str, user_id: int = AUTHOR_ID
) -> None:
    original_message.reply.assert_awaited_once()
    [text] = original_message.reply.await_args.args
    assert text in _get_confirmations(phrases, name, user_id)
    assert original_message.reply.await_args.kwargs == {
        "allowed_mentions": AGENT_REPLY_ALLOWED_MENTIONS
    }


def _get_note(bot: MagicMock) -> str:
    bot.agent_worker.add_transcript_note.assert_awaited_once()
    channel_id, note = bot.agent_worker.add_transcript_note.await_args.args
    assert channel_id == CHANNEL_ID
    return str(note)


def _run[T](get_result: Callable[[], Awaitable[T]]) -> T:
    async def run() -> T:
        return await get_result()

    return asyncio.run(run())


def _get_buttons(view: AgentActionView) -> list[discord.ui.Button]:
    return [item for item in view.children if isinstance(item, discord.ui.Button)]


def _get_sent_modal(interaction: MagicMock) -> CreateEventModal:
    modal = interaction.response.send_modal.await_args.args[0]
    assert isinstance(modal, CreateEventModal)
    return modal


def _create_event(session: sessionmaker[Session], **kwargs: Any) -> int:
    with session() as db_session:
        event = MoobloomEvent(
            name="Hayride",
            start_date=date(2026, 10, 26),
            end_date=date(2026, 10, 26),
            location="Mapleview Farm",
            **kwargs,
        )
        db_session.add(event)
        db_session.commit()
        return event.id


def _get_event(session: sessionmaker[Session], event_id: int) -> MoobloomEvent:
    with session() as db_session:
        event = db_session.get_one(MoobloomEvent, event_id)
        db_session.expunge(event)
        return event


def test_interaction_check__requester__allows_interaction() -> None:
    interaction = _get_interaction()

    async def check() -> bool:
        return await AgentActionView(
            _get_bot(), AUTHOR_ID, _get_original_message(), "Test"
        ).interaction_check(interaction)

    assert _run(check) is True
    interaction.response.send_message.assert_not_awaited()


def _get_tier_phrases(min_attempts: int) -> list[str]:
    return dict(AGENT_NOT_YOUR_BUTTON_MESSAGES)[min_attempts]


def _click(view: AgentActionView, interaction: MagicMock, times: int) -> list[bool]:
    async def click() -> list[bool]:
        return [await view.interaction_check(interaction) for _ in range(times)]

    return _run(click)


def test_interaction_check__someone_else__rejects_with_ephemeral_message() -> None:
    interaction = _get_interaction(user_id=OTHER_USER_ID)

    async def check() -> bool:
        return await AgentActionView(
            _get_bot(), AUTHOR_ID, _get_original_message(), "Test"
        ).interaction_check(interaction)

    assert _run(check) is False
    [message] = interaction.response.send_message.await_args.args
    assert message in _get_tier_phrases(1)
    assert interaction.response.send_message.await_args.kwargs == {"ephemeral": True}


@pytest.mark.parametrize(
    "attempts,min_attempts", [(1, 1), (2, 1), (3, 3), (5, 3), (6, 6), (11, 11), (21, 21), (29, 21)]
)
def test_get_not_your_button_message__picks_tier_by_attempts(
    attempts: int, min_attempts: int
) -> None:
    assert get_not_your_button_message(attempts) in _get_tier_phrases(min_attempts)


def test_button_attempt_counter__counts_per_user() -> None:
    counter = ButtonAttemptCounter(get_time=lambda: 0)

    assert [counter.add_attempt(1), counter.add_attempt(1), counter.add_attempt(2)] == [1, 2, 1]


def test_button_attempt_counter__expired_entries__are_pruned_and_restart() -> None:
    now = 0.0
    counter = ButtonAttemptCounter(get_time=lambda: now)
    counter.add_attempt(1)
    counter.add_attempt(1)
    counter.add_attempt(2)

    now = 3599
    assert counter.add_attempt(1) == 3
    now = 3600
    assert counter.add_attempt(3) == 1
    assert set(counter.attempts) == {1, 3}
    now = 7198
    assert counter.add_attempt(1) == 4
    now = 7198 + 3600
    assert counter.add_attempt(1) == 1
    assert set(counter.attempts) == {1}


def test_button_attempt_counter__reset__removes_user() -> None:
    counter = ButtonAttemptCounter(get_time=lambda: 0)
    counter.add_attempt(1)

    counter.reset(1)

    assert counter.add_attempt(1) == 1


def test_interaction_check__requester__does_not_count_attempts(
    counter: ButtonAttemptCounter,
) -> None:
    view = AgentActionView(_get_bot(), AUTHOR_ID, _get_original_message(), "Test")

    assert _click(view, _get_interaction(), 30) == [True] * 30
    assert counter.attempts == {}


def test_interaction_check__30th_attempt__runs_easter_egg_and_resets_count(
    counter: ButtonAttemptCounter,
) -> None:
    interaction = _get_interaction(user_id=OTHER_USER_ID)
    view = AgentActionView(_get_bot(), AUTHOR_ID, _get_original_message(), "Test")

    results = _click(view, interaction, 31)

    assert results == [False] * 29 + [True, False]
    assert interaction.response.send_message.await_count == 30
    assert interaction.response.send_message.await_args.args[0] in _get_tier_phrases(1)
    assert counter.attempts[OTHER_USER_ID][0] == 1


def test_create_view__easter_egg__opens_modal_for_clicker(
    counter: ButtonAttemptCounter,
) -> None:
    interaction = _get_interaction(user_id=OTHER_USER_ID)
    counter.attempts[OTHER_USER_ID] = (29, counter.get_time())

    async def click() -> None:
        view = CreateEventView(
            _get_bot(), AUTHOR_ID, _get_original_message(), EventFields(name="Hayride")
        )
        if await view.interaction_check(interaction):
            await view.open_form.callback(interaction)

    _run(click)

    assert _get_sent_modal(interaction).name.default == "Hayride"
    interaction.response.send_message.assert_not_awaited()


def test_update_view__easter_egg__opens_modal_for_clicker(
    counter: ButtonAttemptCounter, session: sessionmaker[Session]
) -> None:
    event_id = _create_event(session)
    interaction = _get_interaction(user_id=OTHER_USER_ID)
    counter.attempts[OTHER_USER_ID] = (29, counter.get_time())

    async def click() -> None:
        view = UpdateEventView(
            _get_bot(), AUTHOR_ID, _get_original_message(), event_id, "Hayride", EventFields()
        )
        if await view.interaction_check(interaction):
            await view.open_form.callback(interaction)

    _run(click)

    assert _get_sent_modal(interaction).name.default == "Hayride"


def _get_hayride(**kwargs: Any) -> MoobloomEvent:
    return MoobloomEvent(
        **{
            "id": 1,
            "name": "Hayride",
            "start_date": date(2026, 10, 26),
            "end_date": date(2026, 10, 26),
            "location": "Mapleview Farm",
            **kwargs,
        }
    )


def test_delete_view__easter_egg__deletes_for_clicker(
    counter: ButtonAttemptCounter, mocker: MockerFixture
) -> None:
    delete_event = mocker.patch(
        "moobot.discord.views.agent_action.delete_event",
        AsyncMock(return_value=_get_hayride()),
    )
    bot = _get_bot()
    original_message = _get_original_message()
    interaction = _get_interaction(user_id=OTHER_USER_ID)
    counter.attempts[OTHER_USER_ID] = (29, counter.get_time())

    async def click() -> None:
        view = DeleteEventView(bot, AUTHOR_ID, original_message, 1, "Hayride")
        if await view.interaction_check(interaction):
            await view.delete.callback(interaction)

    _run(click)

    delete_event.assert_awaited_once_with(bot, 1, OTHER_USER_ID)
    interaction.response.send_message.assert_not_awaited()
    assert OTHER_USER_ID not in counter.attempts
    _assert_confirmation_reply(
        original_message, AGENT_EVENT_DELETED_MESSAGES, "Hayride", OTHER_USER_ID
    )
    assert _get_note(bot).startswith(
        f"{NOTE_PREFIX} {_get_author(OTHER_USER_ID)} deleted the event"
    )


def test_create_view__easter_egg_submit__confirms_and_notes_clicker(
    session: sessionmaker[Session],
) -> None:
    bot = _get_bot()
    original_message = _get_original_message()
    interaction = _get_interaction(user_id=OTHER_USER_ID)

    async def submit_form() -> None:
        view = CreateEventView(bot, AUTHOR_ID, original_message, EventFields(name="Hayride"))
        await view.submit_form(bot, interaction, _get_hayride(id=None))

    _run(submit_form)

    _assert_confirmation_reply(
        original_message, AGENT_EVENT_CREATED_MESSAGES, "Hayride", OTHER_USER_ID
    )
    assert _get_note(bot).startswith(
        f"{NOTE_PREFIX} {_get_author(OTHER_USER_ID)} created the event"
    )


@pytest.mark.parametrize("edit_error", [None, discord.HTTPException(MagicMock(status=500), "")])
def test_on_timeout__disables_buttons_and_edits_message(edit_error: Exception | None) -> None:
    message = MagicMock(edit=AsyncMock(side_effect=edit_error))

    async def time_out() -> DeleteEventView:
        view = DeleteEventView(_get_bot(), AUTHOR_ID, _get_original_message(), 1, "Hayride")
        view.message = message
        await view.on_timeout()
        return view

    view = _run(time_out)

    assert [button.disabled for button in _get_buttons(view)] == [True, True]
    message.edit.assert_awaited_once_with(view=view)


def test_create_view__open_form__sends_prefilled_modal() -> None:
    interaction = _get_interaction()
    fields = EventFields(
        name="Hayride",
        time=SEPTEMBER_21_TIME,
        location="Mapleview Farm",
        channel_name="#hayride",
        description="Bring a blanket",
        url="https://example.com/hayride",
        image_url="https://example.com/hayride.png",
    )

    async def open_form() -> None:
        view = CreateEventView(_get_bot(), AUTHOR_ID, _get_original_message(), fields)
        await view.open_form.callback(interaction)

    _run(open_form)

    modal = _get_sent_modal(interaction)
    assert modal.title == "Create a new event"
    assert modal.name.default == "Hayride"
    assert modal.time.default == "September 21 7:00 PM to September 21 10:00 PM"
    assert modal.location.default == "Mapleview Farm"
    assert modal.channel_name.default == "hayride"
    assert modal.description.default == (
        "url:https://example.com/hayride\nimage_url:https://example.com/hayride.png\nBring a"
        " blanket"
    )


def test_create_view__open_form_without_fields__sends_blank_modal() -> None:
    interaction = _get_interaction()

    async def open_form() -> None:
        view = CreateEventView(
            _get_bot(), AUTHOR_ID, _get_original_message(), EventFields(location="Mapleview Farm")
        )
        await view.open_form.callback(interaction)

    _run(open_form)

    modal = _get_sent_modal(interaction)
    assert modal.name.default is None
    assert modal.time.default is None
    assert modal.description.default is None
    assert modal.location.default == "Mapleview Farm"


def test_create_view__submit_form__creates_event_confirms_and_adds_note(
    session: sessionmaker[Session],
) -> None:
    bot = _get_bot()
    original_message = _get_original_message()
    interaction = _get_interaction()
    message = MagicMock(edit=AsyncMock())
    event = MoobloomEvent(
        name="Hayride",
        create_channel=False,
        start_date=SEPTEMBER_21_TIME.start_date,
        start_time=SEPTEMBER_21_TIME.start_time,
        end_date=SEPTEMBER_21_TIME.end_date,
        end_time=SEPTEMBER_21_TIME.end_time,
        location="",
        created_by=AUTHOR_ID,
    )

    async def submit_twice() -> CreateEventView:
        view = CreateEventView(bot, AUTHOR_ID, original_message, EventFields(name="Hayride"))
        view.message = message
        await view.submit_form(bot, interaction, event)
        await view.submit_form(bot, interaction, event)
        return view

    view = _run(submit_twice)

    with session() as db_session:
        [saved_event] = db_session.query(MoobloomEvent).all()
        event_id = saved_event.id
    interaction.response.defer.assert_awaited_once_with()
    interaction.response.send_message.assert_awaited_once_with(
        AGENT_ACTION_ALREADY_USED_MESSAGE, ephemeral=True
    )
    interaction.followup.send.assert_not_awaited()
    _assert_confirmation_reply(original_message, AGENT_EVENT_CREATED_MESSAGES, "Hayride")
    assert _get_note(bot) == (
        f'{NOTE_PREFIX} {_get_author(AUTHOR_ID)} created the event "Hayride" (id {event_id}):'
        " Mon. September 21 7:00 PM-10:00 PM, location: none, channel: none, url: none,"
        " description: none"
    )
    assert [button.disabled for button in _get_buttons(view)] == [True]
    message.edit.assert_awaited_once_with(view=view)


def test_update_view__open_form__prefills_changes_without_changing_event(
    session: sessionmaker[Session],
) -> None:
    event_id = _create_event(session, description="Bring a blanket")
    interaction = _get_interaction()
    fields = EventFields(name="Moonlit Hayride", time=SEPTEMBER_21_TIME)

    async def open_form() -> None:
        view = UpdateEventView(
            _get_bot(), AUTHOR_ID, _get_original_message(), event_id, "Hayride", fields
        )
        await view.open_form.callback(interaction)

    _run(open_form)

    modal = _get_sent_modal(interaction)
    assert modal.title == "Update an event"
    assert modal.name.default == "Moonlit Hayride"
    assert modal.time.default == "September 21 7:00 PM to September 21 10:00 PM"
    assert modal.location.default == "Mapleview Farm"
    assert modal.description.default == "Bring a blanket"
    event = _get_event(session, event_id)
    assert event.name == "Hayride"
    assert event.start_date == date(2026, 10, 26)
    assert event.start_time is None


def test_update_view__open_form_for_deleted_event__sends_error_and_disables_buttons(
    session: sessionmaker[Session],
) -> None:
    event_id = _create_event(session, deleted=True)
    interaction = _get_interaction()

    async def open_form() -> UpdateEventView:
        view = UpdateEventView(
            _get_bot(), AUTHOR_ID, _get_original_message(), event_id, "Hayride", EventFields()
        )
        await view.open_form.callback(interaction)
        return view

    view = _run(open_form)

    interaction.response.send_modal.assert_not_awaited()
    interaction.response.send_message.assert_awaited_once()
    assert [button.disabled for button in _get_buttons(view)] == [True]


def test_update_view__submit_form__updates_event_confirms_and_adds_note(
    session: sessionmaker[Session],
) -> None:
    event_id = _create_event(session, channel_name="hayride", channel_id="555")
    bot = _get_bot()
    original_message = _get_original_message()
    interaction = _get_interaction()
    updated_event = MoobloomEvent(
        name="Moonlit Hayride",
        create_channel=True,
        channel_name="hayride",
        start_date=SEPTEMBER_21_TIME.start_date,
        start_time=SEPTEMBER_21_TIME.start_time,
        end_date=SEPTEMBER_21_TIME.end_date,
        end_time=SEPTEMBER_21_TIME.end_time,
        location="Mapleview Farm",
        description="Bring a blanket",
        url="https://example.com/hayride",
    )

    async def submit_form() -> UpdateEventView:
        view = UpdateEventView(
            bot, AUTHOR_ID, original_message, event_id, "Hayride", EventFields(name="Hay")
        )
        await view.submit_form(bot, interaction, updated_event)
        return view

    view = _run(submit_form)

    event = _get_event(session, event_id)
    assert event.name == "Moonlit Hayride"
    assert event.start_time == SEPTEMBER_21_TIME.start_time
    assert event.out_of_sync is True
    assert event.updated_by == str(AUTHOR_ID)
    interaction.response.defer.assert_awaited_once_with()
    interaction.response.send_message.assert_not_awaited()
    _assert_confirmation_reply(original_message, AGENT_EVENT_UPDATED_MESSAGES, "Moonlit Hayride")
    assert _get_note(bot) == (
        f'{NOTE_PREFIX} {_get_author(AUTHOR_ID)} updated the event "Moonlit Hayride"'
        f" (id {event_id}): Mon. September 21 7:00 PM-10:00 PM, location: Mapleview Farm,"
        " channel: <#555>, url: https://example.com/hayride, description: Bring a blanket"
    )
    assert [button.disabled for button in _get_buttons(view)] == [True]


@pytest.mark.parametrize(
    "error,message",
    [
        (
            UpdateEventError.EVENT_NOT_FOUND,
            "Sorry <@42>, I couldn't locate the event you're updating. It may have been deleted.",
        ),
        (
            UpdateEventError.CHANNEL_NAME_CHANGED,
            "Sorry <@42>, updating event channel name is not currently supported.",
        ),
    ],
)
def test_update_view__submit_form_rejected__sends_ephemeral_error_and_keeps_buttons(
    mocker: MockerFixture, error: UpdateEventError, message: str
) -> None:
    mocker.patch("moobot.discord.views.agent_action.update_event", AsyncMock(return_value=error))
    bot = _get_bot()
    original_message = _get_original_message()
    interaction = _get_interaction()

    async def submit_form() -> UpdateEventView:
        view = UpdateEventView(bot, AUTHOR_ID, original_message, 1, "Hayride", EventFields())
        await view.submit_form(bot, interaction, MoobloomEvent(name="Hayride"))
        return view

    view = _run(submit_form)

    interaction.response.send_message.assert_awaited_once_with(message, ephemeral=True)
    interaction.response.defer.assert_not_awaited()
    original_message.reply.assert_not_awaited()
    bot.agent_worker.add_transcript_note.assert_not_awaited()
    assert [button.disabled for button in _get_buttons(view)] == [False]
    assert view.used is False


def test_delete_view__delete__deletes_confirms_and_adds_note(mocker: MockerFixture) -> None:
    delete_event = mocker.patch(
        "moobot.discord.views.agent_action.delete_event", AsyncMock(return_value=_get_hayride())
    )
    bot = _get_bot()
    original_message = _get_original_message()
    interaction = _get_interaction()

    async def delete() -> DeleteEventView:
        view = DeleteEventView(bot, AUTHOR_ID, original_message, 1, "Hayride")
        await view.delete.callback(interaction)
        return view

    view = _run(delete)

    delete_event.assert_awaited_once_with(bot, 1, AUTHOR_ID)
    interaction.response.edit_message.assert_awaited_once_with(view=view)
    interaction.response.send_message.assert_not_awaited()
    interaction.followup.send.assert_not_awaited()
    assert [button.disabled for button in _get_buttons(view)] == [True, True]
    _assert_confirmation_reply(original_message, AGENT_EVENT_DELETED_MESSAGES, "Hayride")
    assert _get_note(bot) == (
        f'{NOTE_PREFIX} {_get_author(AUTHOR_ID)} deleted the event "Hayride" (id 1):'
        " Mon. October 26, location: Mapleview Farm, channel: none, url: none, description: none"
    )


def test_delete_view__delete_missing_event__sends_ephemeral_error(mocker: MockerFixture) -> None:
    mocker.patch("moobot.discord.views.agent_action.delete_event", AsyncMock(return_value=None))
    bot = _get_bot()
    original_message = _get_original_message()
    interaction = _get_interaction()

    async def delete() -> None:
        view = DeleteEventView(bot, AUTHOR_ID, original_message, 1, "Hayride")
        await view.delete.callback(interaction)

    _run(delete)

    interaction.followup.send.assert_awaited_once_with(
        "Sorry <@42>, I couldn't locate that event. It may have already been deleted.",
        ephemeral=True,
    )
    original_message.reply.assert_not_awaited()
    bot.agent_worker.add_transcript_note.assert_not_awaited()


def test_delete_view__cancel__confirms_and_adds_note_without_deleting(
    mocker: MockerFixture,
) -> None:
    delete_event = mocker.patch("moobot.discord.views.agent_action.delete_event", AsyncMock())
    bot = _get_bot()
    original_message = _get_original_message()
    interaction = _get_interaction()

    async def cancel() -> DeleteEventView:
        view = DeleteEventView(bot, AUTHOR_ID, original_message, 1, "Hayride")
        await view.cancel.callback(interaction)
        return view

    view = _run(cancel)

    delete_event.assert_not_awaited()
    interaction.response.edit_message.assert_awaited_once_with(view=view)
    interaction.response.send_message.assert_not_awaited()
    interaction.followup.send.assert_not_awaited()
    assert [button.disabled for button in _get_buttons(view)] == [True, True]
    _assert_confirmation_reply(original_message, AGENT_EVENT_DELETE_CANCELLED_MESSAGES, "Hayride")
    assert _get_note(bot) == (
        f"{NOTE_PREFIX} {_get_author(AUTHOR_ID)} clicked Cancel instead of deleting the event"
        ' "Hayride" (id 1), so it was not deleted.'
    )


def test_send_confirmation__reply_fails__logs_warning() -> None:
    original_message = _get_original_message()
    original_message.reply.side_effect = discord.HTTPException(MagicMock(status=400), "")

    async def send_confirmation() -> None:
        view = DeleteEventView(_get_bot(), AUTHOR_ID, original_message, 1, "Hayride")
        await view.send_confirmation(_get_interaction(), ["ok {name}"], "Hayride")

    _run(send_confirmation)

    original_message.reply.assert_awaited_once_with(
        "ok Hayride", allowed_mentions=AGENT_REPLY_ALLOWED_MENTIONS
    )
