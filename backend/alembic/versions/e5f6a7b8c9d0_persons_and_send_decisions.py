"""persons and submission send decisions

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8

变更内容：
- 新增 persons 表，按五字段去重；
- submissions 增加 person_id / send_mode / needs_manual；
- 回填所有历史提交的人员关联与发送标记。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.person import Person
from app.models.submission import Submission
from app.services.persons import normalize_person_fields, person_match_key

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "persons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_key", sa.String(64), nullable=False),
        sa.Column("organization", sa.String(512), nullable=False),
        sa.Column("position", sa.String(512), nullable=False),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("has_sent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("first_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("match_key", name="uq_persons_match_key"),
    )
    op.create_index("ix_persons_has_sent", "persons", ["has_sent"])

    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("person_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("send_mode", sa.String(16), nullable=False, server_default="manual")
        )
        batch_op.add_column(
            sa.Column(
                "needs_manual", sa.Boolean(), nullable=False, server_default=sa.text("1")
            )
        )
        batch_op.create_index("ix_submissions_person_id", ["person_id"])
        batch_op.create_index("ix_submissions_needs_manual", ["needs_manual"])
        batch_op.create_foreign_key(
            "fk_submissions_person_id", "persons", ["person_id"], ["id"]
        )

    bind = op.get_bind()
    session = Session(bind=bind)
    people: dict[str, Person] = {}
    for submission in session.scalars(select(Submission).order_by(Submission.id)):
        fields = normalize_person_fields(
            organization=submission.organization,
            position=submission.position,
            name=submission.name,
            phone=submission.phone,
            email=submission.email,
        )
        key = person_match_key(**fields)
        person = people.get(key)
        if person is None:
            person = Person(match_key=key, **fields, has_sent=False)
            session.add(person)
            session.flush()
            people[key] = person

        submission.person_id = person.id
        submission.send_mode = "manual"
        sent = submission.status == "sent" or submission.mail_sent_at is not None
        submission.needs_manual = not sent
        if sent:
            moment = submission.mail_sent_at or submission.updated_at
            person.has_sent = True
            if person.first_sent_at is None:
                person.first_sent_at = moment
            person.last_sent_at = moment

    session.commit()
    session.close()


def downgrade() -> None:
    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_submissions_person_id", type_="foreignkey")
        batch_op.drop_index("ix_submissions_needs_manual")
        batch_op.drop_index("ix_submissions_person_id")
        batch_op.drop_column("needs_manual")
        batch_op.drop_column("send_mode")
        batch_op.drop_column("person_id")

    op.drop_index("ix_persons_has_sent", table_name="persons")
    op.drop_table("persons")
