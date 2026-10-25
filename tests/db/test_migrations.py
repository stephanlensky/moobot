from collections.abc import Generator

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, create_engine, inspect

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
