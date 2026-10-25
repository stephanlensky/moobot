from alembic import context
from sqlalchemy import Connection

from moobot.db.models import Base

target_metadata = Base.metadata


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        run_migrations(connection)
        return

    from moobot.db.session import engine

    with engine.connect() as connection:
        run_migrations(connection)


run_migrations_online()
