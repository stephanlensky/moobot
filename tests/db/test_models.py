from moobot.db.models import MoobloomEvent
from moobot.util.time import now as local_now


def test_moobloom_event__channel_name_provided_with_pound__pound_is_removed() -> None:
    event = MoobloomEvent(name="some event", channel_name="#some-channel", start_date=local_now())
    assert event.channel_name == "some-channel"
