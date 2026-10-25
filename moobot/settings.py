import logging

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )

    tz: str

    # logging config
    log_level: int = logging.DEBUG
    # discord.py is very noisy at DEBUG (it logs raw gateway payloads), so default it lower
    discord_log_level: int = logging.INFO
    log_format: str = "%(asctime)s [%(process)d] [%(levelname)s] %(name)-16s %(message)s"
    log_date_format: str = "%Y-%m-%d %H:%M:%S"

    # db credentials
    postgres_host: str = "db"
    postgres_user: str
    postgres_password: str

    discord_token: str

    # event listing config
    calendar_channel_id: int
    event_announce_channel_id: int
    rsvp_yes_emoji: str = "✅"
    rsvp_maybe_emoji: str = "❓"
    rsvp_no_emoji: str = "❌"
    get_all_event_channels_react_emoji_name: str
    google_calendar_sync_react_emoji_name: str
    google_calendar_birthday_sync_react_emoji: str = "🎂"
    all_events_role_name: str
    active_events_category_name: str

    google_calendar_sync_calendar_name: str = "Moobloom Events"
    google_calendar_sync_birthday_calendar_name: str = "Moobloom Birthdays"

    # google api credentials for gcalendar integration
    google_client_id: str
    google_project_id: str
    google_client_secret: str
    google_redirect_uri_host: str

    # conversational agent
    litellm_base_url: str = "http://litellm.litellm.svc.cluster.local/v1"
    litellm_api_key: str | None = None
    agent_model: str = "openrouter/z-ai/glm-5.3-flash"
    agent_max_turns: int = 10

    # s3 storage for agent transcripts
    s3_endpoint_url: str = "http://seaweedfs.seaweedfs.svc.cluster.local:8333"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_bucket: str = "moobot"


def get_settings() -> Settings:
    return Settings()  # type: ignore
