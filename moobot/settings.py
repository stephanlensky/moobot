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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    return Settings()
