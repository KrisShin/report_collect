"""reports and submission report_id

Revision ID: 39a043166651
Revises: 98300a6312cd
Create Date: 2026-10-10 15:19:29.558298

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "39a043166651"
down_revision: str | None = "98300a6312cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "fk_submissions_report_id_reports"


def upgrade() -> None:
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
        batch_op.create_index(batch_op.f("ix_reports_is_active"), ["is_active"], unique=False)

    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("report_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_submissions_report_id"), ["report_id"], unique=False)
        batch_op.create_foreign_key(FK_NAME, "reports", ["report_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.drop_constraint(FK_NAME, type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_submissions_report_id"))
        batch_op.drop_column("report_id")

    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_reports_is_active"))

    op.drop_table("reports")
