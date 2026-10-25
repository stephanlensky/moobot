"""add google auth code verifier

Revision ID: e98a2ff69682
Revises: 3b8b5dbbc9d1
Create Date: 2026-10-25 10:30:08.223918

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e98a2ff69682"
down_revision: str | None = "3b8b5dbbc9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DELETE FROM googleapiauthsession")
    with op.batch_alter_table("googleapiauthsession", schema=None) as batch_op:
        batch_op.add_column(sa.Column("code_verifier", sa.String(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("googleapiauthsession", schema=None) as batch_op:
        batch_op.drop_column("code_verifier")
