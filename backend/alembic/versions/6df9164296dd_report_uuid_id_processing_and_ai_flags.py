"""report uuid id processing and ai flags

Revision ID: 6df9164296dd
Revises: 39a043166651
Create Date: 2026-10-10 16:05:00.000000

变更内容：
- reports.id 由自增整数改为 32 位 uuid4 hex 字符串
- submissions.report_id 同步改为 String(32)
- submissions 增加处理状态（is_processed / processed_at / processed_action）
- submissions 增加 AI 判定字段（ai_flag / ai_score / ai_reason）
- submissions 增加唯一约束：同一报告 + 同一手机号只能提交一次
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6df9164296dd"
down_revision: str | None = "39a043166651"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_REPORT = "fk_submissions_report_id_reports"
UQ_REPORT_PHONE = "uq_submissions_report_phone"


def upgrade() -> None:
    # 1) 先移除旧的整型 report_id 及其约束/索引
    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.drop_constraint(FK_REPORT, type_="foreignkey")
        batch_op.drop_index("ix_submissions_report_id")
        batch_op.drop_column("report_id")

    # 2) 重建 reports 表：字符串主键
    op.drop_table("reports")
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.create_index("ix_reports_is_active", ["is_active"], unique=False)

    # 3) submissions 增加新列、索引与唯一约束
    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("report_id", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column("is_processed", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("processed_action", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("ai_flag", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("ai_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("ai_reason", sa.String(length=512), nullable=True))
        batch_op.create_index("ix_submissions_report_id", ["report_id"], unique=False)
        batch_op.create_index("ix_submissions_is_processed", ["is_processed"], unique=False)
        batch_op.create_index("ix_submissions_ai_flag", ["ai_flag"], unique=False)
        batch_op.create_foreign_key(FK_REPORT, "reports", ["report_id"], ["id"])
        batch_op.create_unique_constraint(UQ_REPORT_PHONE, ["report_id", "phone"])


def downgrade() -> None:
    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.drop_constraint(UQ_REPORT_PHONE, type_="unique")
        batch_op.drop_constraint(FK_REPORT, type_="foreignkey")
        batch_op.drop_index("ix_submissions_ai_flag")
        batch_op.drop_index("ix_submissions_is_processed")
        batch_op.drop_index("ix_submissions_report_id")
        batch_op.drop_column("ai_reason")
        batch_op.drop_column("ai_score")
        batch_op.drop_column("ai_flag")
        batch_op.drop_column("processed_action")
        batch_op.drop_column("processed_at")
        batch_op.drop_column("is_processed")
        batch_op.drop_column("report_id")

    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.drop_index("ix_reports_is_active")
    op.drop_table("reports")
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.create_index("ix_reports_is_active", ["is_active"], unique=False)

    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("report_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_submissions_report_id", ["report_id"], unique=False)
        batch_op.create_foreign_key(FK_REPORT, "reports", ["report_id"], ["id"])
