import logging
import sys

from moobot.settings import get_settings


def _configure_logging() -> None:
    settings = get_settings()
    stdout_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(settings.log_format, settings.log_date_format)
    stdout_handler.setFormatter(formatter)

    notifier_bot_root_logger = logging.getLogger(__name__)
    notifier_bot_root_logger.propagate = False
    notifier_bot_root_logger.addHandler(stdout_handler)
    notifier_bot_root_logger.setLevel(settings.log_level)

    # discord.py logs its own errors (including exceptions raised inside autocomplete callbacks,
    # which it swallows rather than re-raising) to the `discord` logger hierarchy. Without a handler
    # here those records are dropped silently.
    discord_logger = logging.getLogger("discord")
    discord_logger.propagate = False
    discord_logger.addHandler(stdout_handler)
    discord_logger.setLevel(settings.discord_log_level)


_configure_logging()
