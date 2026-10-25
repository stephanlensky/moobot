"""add birthdays and calendar sync types

Revision ID: 4741e17741c7
Revises: 3a279880598c
Create Date: 2026-10-25 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4741e17741c7"
down_revision: str | None = "3a279880598c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    calendars = connection.execute(
        sa.text("SELECT user_id, calendar_id, created_at FROM googlecalendar").columns(
            created_at=sa.DateTime
        )
    ).fetchall()
    op.drop_table("googlecalendar")
    googlecalendar = op.create_table(
        "googlecalendar",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("calendar_type", sa.String(), nullable=False),
        sa.Column("calendar_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "calendar_type"),
    )
    if calendars:
        op.bulk_insert(
            googlecalendar,
            [
                {
                    "user_id": user_id,
                    "calendar_type": "events",
                    "calendar_id": calendar_id,
                    "created_at": created_at,
                }
                for user_id, calendar_id, created_at in calendars
            ],
        )

    op.create_table(
        "googlecalendarsync",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("calendar_type", sa.String(), nullable=False),
        sa.Column("setup_finished", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "calendar_type"),
    )
    op.execute(
        "INSERT INTO googlecalendarsync (user_id, calendar_type, setup_finished, created_at) "
        "SELECT user_id, 'events', setup_finished, created_at FROM googleapiuser"
    )
    with op.batch_alter_table("googleapiuser", schema=None) as batch_op:
        batch_op.drop_column("setup_finished")

    with op.batch_alter_table("googleapiauthsession", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("calendar_type", sa.String(), nullable=False, server_default="events")
        )
    with op.batch_alter_table("googleapiauthsession", schema=None) as batch_op:
        batch_op.alter_column("calendar_type", server_default=None)

    op.create_table(
        "birthday",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("birthday")

    with op.batch_alter_table("googleapiauthsession", schema=None) as batch_op:
        batch_op.drop_column("calendar_type")

    op.execute(
        "DELETE FROM googleapiuser WHERE user_id NOT IN ("
        "SELECT user_id FROM googlecalendarsync WHERE calendar_type = 'events')"
    )
    with op.batch_alter_table("googleapiuser", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("setup_finished", sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.execute(
        "UPDATE googleapiuser SET setup_finished = ("
        "SELECT setup_finished FROM googlecalendarsync "
        "WHERE googlecalendarsync.user_id = googleapiuser.user_id "
        "AND googlecalendarsync.calendar_type = 'events')"
    )
    with op.batch_alter_table("googleapiuser", schema=None) as batch_op:
        batch_op.alter_column("setup_finished", server_default=None)
    op.drop_table("googlecalendarsync")

    connection = op.get_bind()
    calendars = connection.execute(
        sa.text(
            "SELECT user_id, calendar_id, created_at FROM googlecalendar "
            "WHERE calendar_type = 'events'"
        ).columns(created_at=sa.DateTime)
    ).fetchall()
    op.drop_table("googlecalendar")
    googlecalendar = op.create_table(
        "googlecalendar",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("calendar_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    if calendars:
        op.bulk_insert(
            googlecalendar,
            [
                {"user_id": user_id, "calendar_id": calendar_id, "created_at": created_at}
                for user_id, calendar_id, created_at in calendars
            ],
        )
