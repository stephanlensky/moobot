"""initial schema

Revision ID: 92324d85ef93
Revises:
Create Date: 2026-10-25 10:29:04.273670

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "92324d85ef93"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "googleapiauthsession",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state"),
    )
    op.create_table(
        "googleapiuser",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("refresh_token", sa.String(), nullable=False),
        sa.Column("token_uri", sa.String(), nullable=False),
        sa.Column("scopes", sa.String(), nullable=False),
        sa.Column("calendar_id", sa.String(), nullable=True),
        sa.Column("setup_finished", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "moobloomevent",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("create_channel", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("channel_name", sa.String(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("thumbnail_url", sa.String(), nullable=True),
        sa.Column("announcement_message_id", sa.String(), nullable=True),
        sa.Column("channel_id", sa.String(), nullable=True),
        sa.Column("channel_introduction_message_id", sa.String(), nullable=True),
        sa.Column("out_of_sync", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "reactions_created", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "moobloomeventrsvp",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("attendance_type", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("moobloomeventrsvp")
    op.drop_table("moobloomevent")
    op.drop_table("googleapiuser")
    op.drop_table("googleapiauthsession")
