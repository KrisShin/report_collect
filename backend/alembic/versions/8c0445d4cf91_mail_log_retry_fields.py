"""mail log retry fields

Revision ID: 8c0445d4cf91
Revises: 41b31565d693

变更内容：mail_logs 增加 failed_submission_ids（本轮失败的记录 id）
与 retry_of（重试来源 mail_log id），用于"一键重试失败"。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c0445d4cf91"
down_revision: str | None = "41b31565d693"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mail_logs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("failed_submission_ids", sa.Text(), nullable=False, server_default="[]")
        )
        batch_op.add_column(sa.Column("retry_of", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("mail_logs", schema=None) as batch_op:
        batch_op.drop_column("retry_of")
        batch_op.drop_column("failed_submission_ids")
