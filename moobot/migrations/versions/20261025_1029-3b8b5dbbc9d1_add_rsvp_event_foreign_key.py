"""add rsvp event foreign key

Revision ID: 3b8b5dbbc9d1
Revises: 92324d85ef93
Create Date: 2026-10-25 10:29:28.399615

"""

from collections.abc import Sequence

from alembic import op

revision: str = "3b8b5dbbc9d1"
down_revision: str | None = "92324d85ef93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("moobloomeventrsvp", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "moobloomeventrsvp_event_id_fkey", "moobloomevent", ["event_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("moobloomeventrsvp", schema=None) as batch_op:
        batch_op.drop_constraint("moobloomeventrsvp_event_id_fkey", type_="foreignkey")
