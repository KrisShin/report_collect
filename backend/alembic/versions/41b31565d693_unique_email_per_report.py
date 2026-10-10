"""unique email per report

Revision ID: 41b31565d693
Revises: b8b47959bf9d

变更内容：submissions 增加 (report_id, email) 唯一约束，
保证同一报告内同一邮箱只能提交一次（与 phone 约束一致）。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "41b31565d693"
down_revision: str | None = "b8b47959bf9d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UQ_REPORT_EMAIL = "uq_submissions_report_email"


def upgrade() -> None:
    # 历史重复数据清理：同一报告 + 同一邮箱保留最早一条
    op.execute(
        """
        DELETE FROM submissions
        WHERE id NOT IN (
            SELECT MIN(id) FROM submissions GROUP BY report_id, lower(email)
        )
        """
    )
    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.create_unique_constraint(UQ_REPORT_EMAIL, ["report_id", "email"])


def downgrade() -> None:
    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.drop_constraint(UQ_REPORT_EMAIL, type_="unique")
