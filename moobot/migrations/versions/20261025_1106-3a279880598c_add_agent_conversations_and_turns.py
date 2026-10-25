"""add agent conversations and turns

Revision ID: 3a279880598c
Revises: 8645224f28b1
Create Date: 2026-10-25 11:06:20.797656

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3a279880598c"
down_revision: str | None = "8645224f28b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agentconversation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("transcript_key", sa.String(), nullable=False),
        sa.Column("last_seen_message_id", sa.String(), nullable=True),
        sa.Column("cleared_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "agentconversation_channel_id_active_key",
        "agentconversation",
        ["channel_id"],
        unique=True,
        postgresql_where=sa.text("cleared_at IS NULL"),
        sqlite_where=sa.text("cleared_at IS NULL"),
    )
    op.create_table(
        "agentturn",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("author_id", sa.String(), nullable=False),
        sa.Column("author_name", sa.String(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("prompt", sa.String(), nullable=True),
        sa.Column("output", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("response_message_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agentconversation.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )


def downgrade() -> None:
    op.drop_table("agentturn")
    op.drop_table("agentconversation")
