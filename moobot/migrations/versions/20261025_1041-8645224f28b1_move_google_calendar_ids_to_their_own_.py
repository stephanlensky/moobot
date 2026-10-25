"""move google calendar ids to their own table

Revision ID: 8645224f28b1
Revises: e98a2ff69682
Create Date: 2026-10-25 10:41:35.224672

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8645224f28b1"
down_revision: str | None = "e98a2ff69682"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "googlecalendar",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("calendar_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.execute(
        "INSERT INTO googlecalendar (user_id, calendar_id, created_at) "
        "SELECT user_id, calendar_id, CURRENT_TIMESTAMP FROM googleapiuser "
        "WHERE calendar_id IS NOT NULL"
    )
    with op.batch_alter_table("googleapiuser", schema=None) as batch_op:
        batch_op.drop_column("calendar_id")


def downgrade() -> None:
    with op.batch_alter_table("googleapiuser", schema=None) as batch_op:
        batch_op.add_column(sa.Column("calendar_id", sa.String(), nullable=True))
    op.execute(
        "UPDATE googleapiuser SET calendar_id = ("
        "SELECT calendar_id FROM googlecalendar "
        "WHERE googlecalendar.user_id = googleapiuser.user_id)"
    )
    op.drop_table("googlecalendar")
