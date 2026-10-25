from collections.abc import Generator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, create_engine, inspect, text

from moobot.db.migrations import alembic_config, head_revision
from moobot.db.models import Base


@pytest.fixture
def connection() -> Generator[Connection]:
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        yield connection
    engine.dispose()


def _upgrade(connection: Connection, revision: str) -> None:
    config = alembic_config()
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


def _downgrade(connection: Connection, revision: str) -> None:
    config = alembic_config()
    config.attributes["connection"] = connection
    command.downgrade(config, revision)


def test_upgrade__from_empty_database__matches_models(connection: Connection) -> None:
    _upgrade(connection, "head")

    context = MigrationContext.configure(connection, opts={"compare_type": True})
    assert context.get_current_revision() == head_revision()
    assert compare_metadata(context, Base.metadata) == []


def test_downgrade__to_base__removes_all_tables(connection: Connection) -> None:
    _upgrade(connection, "head")
    _downgrade(connection, "base")

    assert inspect(connection).get_table_names() == ["alembic_version"]


def test_upgrade__calendar_sync_types__backfills_existing_event_sync(
    connection: Connection,
) -> None:
    _upgrade(connection, "3a279880598c")
    connection.execute(
        text(
            "INSERT INTO googleapiuser (user_id, token, refresh_token, token_uri, scopes,"
            " setup_finished, created_at) VALUES"
            " ('1', 't', 'r', 'u', 's', 1, '2026-01-01 00:00:00'),"
            " ('2', 't', 'r', 'u', 's', 0, '2026-01-01 00:00:00')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO googlecalendar (user_id, calendar_id, created_at) VALUES"
            " ('1', 'calendar-1', '2026-01-01 00:00:00'),"
            " ('3', 'calendar-3', '2026-01-01 00:00:00')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO googleapiauthsession (state, code_verifier, user_id, created_at)"
            " VALUES ('state', 'verifier', '4', '2026-01-01 00:00:00')"
        )
    )

    _upgrade(connection, "head")

    assert connection.execute(
        text("SELECT user_id, calendar_type, calendar_id FROM googlecalendar ORDER BY user_id")
    ).fetchall() == [("1", "events", "calendar-1"), ("3", "events", "calendar-3")]
    assert connection.execute(
        text(
            "SELECT user_id, calendar_type, setup_finished FROM googlecalendarsync ORDER BY user_id"
        )
    ).fetchall() == [("1", "events", 1), ("2", "events", 0)]
    assert connection.execute(
        text("SELECT calendar_type FROM googleapiauthsession")
    ).fetchall() == [("events",)]

    _downgrade(connection, "3a279880598c")

    assert connection.execute(
        text("SELECT user_id, setup_finished FROM googleapiuser ORDER BY user_id")
    ).fetchall() == [("1", 1), ("2", 0)]
    assert connection.execute(
        text("SELECT user_id, calendar_id FROM googlecalendar ORDER BY user_id")
    ).fetchall() == [("1", "calendar-1"), ("3", "calendar-3")]
