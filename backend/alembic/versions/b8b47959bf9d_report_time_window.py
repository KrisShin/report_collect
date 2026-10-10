"""report time window

Revision ID: b8b47959bf9d
Revises: 6df9164296dd

变更内容：reports 增加 start_at / end_at（填报时间段，可空表示不限制）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8b47959bf9d"
down_revision: str | None = "6df9164296dd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.add_column(sa.Column("start_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("end_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.drop_column("end_at")
        batch_op.drop_column("start_at")
