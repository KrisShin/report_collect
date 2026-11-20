"""report email assets

Revision ID: c3d4e5f6a7b8
Revises: 8c0445d4cf91

变更内容：reports 增加报告级邮件主题与 HTML 模板字段。
全部可空；为空时回退全局模板/附件/默认主题，不影响已有报告。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "8c0445d4cf91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email_subject", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("email_template_html", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("email_template_name", sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column("email_template_updated_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.drop_column("email_template_updated_at")
        batch_op.drop_column("email_template_name")
        batch_op.drop_column("email_template_html")
        batch_op.drop_column("email_subject")
