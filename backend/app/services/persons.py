"""跨报告人员去重与发送标记。"""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.person import Person
from app.models.submission import Submission


def normalize_person_fields(
    *,
    organization: str | None,
    position: str | None,
    name: str | None,
    phone: str | None,
    email: str | None,
) -> dict[str, str]:
    """五个字段去首尾空格；邮箱统一小写，其余字段保持大小写。"""

    return {
        "organization": (organization or "").strip(),
        "position": (position or "").strip(),
        "name": (name or "").strip(),
        "phone": (phone or "").strip(),
        "email": (email or "").strip().lower(),
    }


def person_match_key(
    *,
    organization: str | None,
    position: str | None,
    name: str | None,
    phone: str | None,
    email: str | None,
) -> str:
    fields = normalize_person_fields(
        organization=organization,
        position=position,
        name=name,
        phone=phone,
        email=email,
    )
    payload = json.dumps(
        [
            fields["organization"],
            fields["position"],
            fields["name"],
            fields["phone"],
            fields["email"],
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def get_or_create_person(
    db: AsyncSession,
    *,
    organization: str,
    position: str,
    name: str,
    phone: str,
    email: str,
) -> Person:
    """按五字段规范化后的 match_key 去重；并发提交依赖唯一索引。"""

    fields = normalize_person_fields(
        organization=organization,
        position=position,
        name=name,
        phone=phone,
        email=email,
    )
    key = person_match_key(**fields)
    now = datetime.now(UTC)

    await db.execute(
        sqlite_insert(Person)
        .values(
            match_key=key,
            **fields,
            has_sent=False,
            first_sent_at=None,
            last_sent_at=None,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["match_key"])
    )
    person = await db.scalar(select(Person).where(Person.match_key == key))
    if person is None:
        raise RuntimeError("人员信息创建失败")
    return person


async def has_sent_in_other_report(
    db: AsyncSession, person_id: int, report_id: str
) -> bool:
    """该人员是否在**其他报告**中成功发送过邮件。"""

    exists = await db.scalar(
        select(Submission.id)
        .where(Submission.person_id == person_id)
        .where(Submission.report_id != report_id)
        .where(
            or_(
                Submission.status == "sent",
                Submission.mail_sent_at.is_not(None),
            )
        )
        .limit(1)
    )
    return exists is not None


async def mark_person_sent(
    db: AsyncSession, submission: Submission, sent_at: datetime
) -> Person:
    """发送成功后更新人员的全局发送标记。"""

    person = (
        await db.get(Person, submission.person_id)
        if submission.person_id
        else None
    )
    if person is None:
        person = await get_or_create_person(
            db,
            organization=submission.organization,
            position=submission.position,
            name=submission.name,
            phone=submission.phone,
            email=submission.email,
        )
        submission.person_id = person.id

    if not person.has_sent:
        person.has_sent = True
        if person.first_sent_at is None:
            person.first_sent_at = sent_at
    person.last_sent_at = sent_at
    return person
