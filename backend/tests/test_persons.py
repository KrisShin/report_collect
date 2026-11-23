"""人员去重与发送标记。"""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.models.person import Person
from app.models.report import Report
from app.models.submission import Submission
from app.services.persons import (
    get_or_create_person,
    has_sent_in_other_report,
    mark_person_sent,
    normalize_person_fields,
    person_match_key,
)


def test_normalize_person_fields():
    fields = normalize_person_fields(
        organization=" 单位 ",
        position=" 职务 ",
        name=" 张三 ",
        phone=" 13800138000 ",
        email=" ZhangSan@Example.COM ",
    )
    assert fields == {
        "organization": "单位",
        "position": "职务",
        "name": "张三",
        "phone": "13800138000",
        "email": "zhangsan@example.com",
    }


def test_person_match_key_normalizes_trim_and_email_case():
    first = person_match_key(
        organization=" 清华大学 ",
        position=" 研究员 ",
        name=" 张三 ",
        phone=" 13800138000 ",
        email=" ZhangSan@Example.COM ",
    )
    second = person_match_key(
        organization="清华大学",
        position="研究员",
        name="张三",
        phone="13800138000",
        email="zhangsan@example.com",
    )
    assert first == second

    # 非邮箱字段区分大小写
    upper = person_match_key(
        organization="Tsinghua University",
        position="Researcher",
        name="Zhang San",
        phone="13800138000",
        email="zhangsan@example.com",
    )
    lower = person_match_key(
        organization="tsinghua university",
        position="Researcher",
        name="Zhang San",
        phone="13800138000",
        email="zhangsan@example.com",
    )
    assert upper != lower


async def test_get_or_create_person_dedupes():
    async with AsyncSessionLocal() as db:
        first = await get_or_create_person(
            db,
            organization="单位",
            position="职务",
            name="张三",
            phone="13800138000",
            email="a@example.com",
        )
        second = await get_or_create_person(
            db,
            organization=" 单位 ",
            position=" 职务 ",
            name=" 张三 ",
            phone=" 13800138000 ",
            email="A@EXAMPLE.COM",
        )
        await db.commit()

        assert first.id == second.id
        count = await db.scalar(select(func.count()).select_from(Person))
        assert count == 1


async def test_has_sent_in_other_report():
    async with AsyncSessionLocal() as db:
        person = await get_or_create_person(
            db,
            organization="单位",
            position="职务",
            name="张三",
            phone="13800138000",
            email="a@example.com",
        )
        report_a = Report(id="a" * 32, title="报告 A")
        report_b = Report(id="b" * 32, title="报告 B")
        db.add_all([report_a, report_b])
        await db.flush()

        db.add(
            Submission(
                report_id=report_a.id,
                person_id=person.id,
                organization=person.organization,
                position=person.position,
                name=person.name,
                phone=person.phone,
                email=person.email,
                status="sent",
                send_mode="manual",
                needs_manual=False,
                mail_sent_at=datetime.now(UTC),
            )
        )
        await db.commit()

        assert await has_sent_in_other_report(db, person.id, report_b.id) is True
        # 同一报告不算“其他报告”
        assert await has_sent_in_other_report(db, person.id, report_a.id) is False


async def test_mark_person_sent_updates_first_and_last():
    async with AsyncSessionLocal() as db:
        person = await get_or_create_person(
            db,
            organization="单位",
            position="职务",
            name="张三",
            phone="13800138000",
            email="a@example.com",
        )
        report = Report(id="c" * 32, title="报告 C")
        db.add(report)
        await db.flush()
        submission = Submission(
            report_id=report.id,
            person_id=person.id,
            organization=person.organization,
            position=person.position,
            name=person.name,
            phone=person.phone,
            email=person.email,
            status="pending",
        )
        db.add(submission)
        await db.commit()

        first_time = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
        await mark_person_sent(db, submission, first_time)
        await db.commit()
        await db.refresh(person)
        assert person.has_sent is True
        assert person.first_sent_at is not None
        assert person.first_sent_at.replace(tzinfo=UTC) == first_time

        second_time = datetime(2026, 2, 1, 9, 0, tzinfo=UTC)
        await mark_person_sent(db, submission, second_time)
        await db.commit()
        await db.refresh(person)
        assert person.first_sent_at.replace(tzinfo=UTC) == first_time
        assert person.last_sent_at.replace(tzinfo=UTC) == second_time


async def test_mark_person_sent_backfills_missing_person_link():
    async with AsyncSessionLocal() as db:
        report = Report(id="d" * 32, title="报告 D")
        db.add(report)
        await db.flush()
        submission = Submission(
            report_id=report.id,
            person_id=None,
            organization="单位 D",
            position="职务 D",
            name="李四",
            phone="13900139000",
            email="lisi@example.com",
            status="pending",
        )
        db.add(submission)
        await db.commit()

        await mark_person_sent(db, submission, datetime.now(UTC))
        await db.commit()
        await db.refresh(submission)

        assert submission.person_id is not None
        person = await db.get(Person, submission.person_id)
        assert person is not None
        assert person.has_sent is True
