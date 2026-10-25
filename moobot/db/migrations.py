import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, inspect

from moobot.db.session import engine

_logger = logging.getLogger(__name__)

MIGRATIONS_PATH = Path(__file__).parent.parent / "migrations"
ALEMBIC_INI_PATH = Path(__file__).parent.parent.parent / "alembic.ini"


class SchemaOutdatedError(Exception):
    pass


def alembic_config() -> Config:
    config = Config(ALEMBIC_INI_PATH if ALEMBIC_INI_PATH.is_file() else None)
    config.set_main_option("script_location", str(MIGRATIONS_PATH))
    return config


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if head is None:
        raise SchemaOutdatedError("No migration revisions found.")
    return head


def initial_revision() -> str:
    base = ScriptDirectory.from_config(alembic_config()).get_base()
    if base is None:
        raise SchemaOutdatedError("No migration revisions found.")
    return base


def _get_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def _has_user_tables(connection: Connection) -> bool:
    return any(name != "alembic_version" for name in inspect(connection).get_table_names())


def current_revision() -> str | None:
    with engine.connect() as connection:
        return _get_revision(connection)


def check_schema_current() -> None:
    revision = current_revision()
    head = head_revision()
    if revision != head:
        raise SchemaOutdatedError(
            f"Database schema is at {revision or 'unversioned'}, but the code expects {head}.\n"
            "Run 'python -m moobot.db upgrade' to migrate it."
        )


def upgrade_database() -> str:
    with engine.connect() as connection:
        has_tables = _has_user_tables(connection)
        revision = _get_revision(connection)

    if has_tables and revision is None:
        target = initial_revision()
        _logger.info(f"Stamping existing database with revision {target}")
        command.stamp(alembic_config(), target)

    command.upgrade(alembic_config(), "head")

    revision = current_revision()
    _logger.info(f"Database is now at revision {revision}")
    return revision or "base"
