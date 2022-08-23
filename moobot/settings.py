import logging

from pydantic import BaseSettings


class Settings(BaseSettings):
    # logging config
    log_level: int = logging.DEBUG
    log_format: str = "%(asctime)s [%(process)d] [%(levelname)s] %(name)-16s %(message)s"
    log_date_format: str = "%Y-%m-%d %H:%M:%S"

    # db credentials
    postgres_user: str
    postgres_password: str

    discord_token: str

    # event listing config
    calendar_channel_id: int
    event_announce_channel_id: int
    rsvp_yes_emoji: str = "✅"
    rsvp_maybe_emoji: str = "❓"
    rsvp_no_emoji: str = "❌"
    get_all_event_channels_react_emoji_name: str = "toadping"
    all_events_role_name: str = "all-events"
    active_events_category_name: str = "Moobloom Events"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    return Settings()
