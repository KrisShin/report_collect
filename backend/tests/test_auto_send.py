"""已发送人员匹配后的自动发送 / 人工标记。"""

import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.api import routes_client
from app.db.session import AsyncSessionLocal
from app.models.mail_log import MailLog
from app.models.person import Person
from app.models.submission import Submission
from app.services import tasks
from app.services.email_template import default_subject

BASE_PERSON = {
    "organization": "测试单位",
    "position": "测试职务",
    "name": "张三",
    "phone": "13800138000",
    "email": "zhangsan@example.com",
}


async def create_report(admin_client, title: str) -> str:
    response = await admin_client.post("/api/admin/reports", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


async def submit(client, report_id: str, payload: dict):
    return await client.post(
        "/api/client/submissions", json={**payload, "report_id": report_id}
    )


async def _mark_submission_sent(submission_id: int) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.get(Submission, submission_id)
        assert row is not None
        now = datetime.now(UTC)
        row.status = "sent"
        row.mail_sent_at = now
        row.is_processed = True
        row.needs_manual = False
        person = await db.get(Person, row.person_id) if row.person_id else None
        if person is not None:
            person.has_sent = True
            person.first_sent_at = person.first_sent_at or now
            person.last_sent_at = now
        await db.commit()


async def test_new_person_requires_manual(client, admin_client, monkeypatch):
    report_id = await create_report(admin_client, "报告 A")
    queued: list[dict] = []

    async def fake_enqueue(_background, job: str, **payload) -> str:
        queued.append({"job": job, **payload})
        return "inline"

    monkeypatch.setattr(routes_client, "enqueue", fake_enqueue)

    response = await submit(client, report_id, BASE_PERSON)
    assert response.status_code == 201
    submission_id = response.json()["id"]

    assert [item["job"] for item in queued] == ["submission_process"]
    async with AsyncSessionLocal() as db:
        row = await db.get(Submission, submission_id)
        assert row is not None
        assert row.send_mode == "manual"
        assert row.needs_manual is True
        assert row.person_id is not None


async def test_known_sent_person_auto_sends(client, admin_client, monkeypatch):
    report_a = await create_report(admin_client, "报告 A")
    report_b = await create_report(admin_client, "报告 B")

    first = await submit(client, report_a, BASE_PERSON)
    assert first.status_code == 201
    await _mark_submission_sent(first.json()["id"])

    queued: list[dict] = []

    async def fake_enqueue(_background, job: str, **payload) -> str:
        queued.append({"job": job, **payload})
        return "inline"

    monkeypatch.setattr(routes_client, "enqueue", fake_enqueue)

    second = await submit(client, report_b, BASE_PERSON)
    assert second.status_code == 201
    second_id = second.json()["id"]

    report_mail = next(item for item in queued if item["job"] == "report_mail")
    assert report_mail["submission_ids"] == [second_id]

    async with AsyncSessionLocal() as db:
        row = await db.get(Submission, second_id)
        assert row is not None
        assert row.send_mode == "auto"
        assert row.needs_manual is False

        log = await db.get(MailLog, report_mail["log_id"])
        assert log is not None
        assert log.recipient == BASE_PERSON["email"]
        assert log.subject == default_subject("报告 B")
        assert json.loads(log.submission_ids) == [second_id]


async def test_auto_send_failure_requires_manual(client, admin_client, monkeypatch):
    report_a = await create_report(admin_client, "报告 A")
    report_b = await create_report(admin_client, "报告 B")

    first = await submit(client, report_a, BASE_PERSON)
    assert first.status_code == 201
    await _mark_submission_sent(first.json()["id"])

    queued: list[dict] = []

    async def fake_enqueue(_background, job: str, **payload) -> str:
        queued.append({"job": job, **payload})
        return "inline"

    monkeypatch.setattr(routes_client, "enqueue", fake_enqueue)

    second = await submit(client, report_b, BASE_PERSON)
    assert second.status_code == 201
    second_id = second.json()["id"]
    log_id = next(
        item["log_id"] for item in queued if item["job"] == "report_mail"
    )

    async def fake_send_mails(mails, **_kwargs):
        return ["boom"] * len(mails)

    async def fake_notify(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(tasks, "send_mails", fake_send_mails)
    monkeypatch.setattr(tasks, "_notify_feishu_safe", fake_notify)
    monkeypatch.setattr(tasks, "_notify_feishu_card_safe", fake_notify)

    await tasks.deliver_report_mail(log_id, [second_id])

    async with AsyncSessionLocal() as db:
        row = await db.get(Submission, second_id)
        assert row is not None
        assert row.send_mode == "auto"
        assert row.needs_manual is True
        assert row.status == "pending"
        assert row.mail_error == "boom"
        person = await db.get(Person, row.person_id)
        assert person is not None
        assert person.has_sent is True


async def test_manual_send_marks_person_sent(client, admin_client, monkeypatch):
    report_id = await create_report(admin_client, "报告 C")
    response = await submit(client, report_id, BASE_PERSON)
    assert response.status_code == 201
    submission_id = response.json()["id"]

    queued: list[dict] = []

    async def fake_enqueue(_background, job: str, **payload) -> str:
        queued.append({"job": job, **payload})
        return "inline"

    monkeypatch.setattr("app.api.routes_admin.enqueue", fake_enqueue)

    sent = await admin_client.post(
        "/api/admin/submissions/send-mail", json={"ids": [submission_id]}
    )
    assert sent.status_code == 200
    log_id = sent.json()["log_id"]

    async def fake_send_mails(mails, **_kwargs):
        return [None] * len(mails)

    async def fake_notify(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(tasks, "send_mails", fake_send_mails)
    monkeypatch.setattr(tasks, "_notify_feishu_safe", fake_notify)
    monkeypatch.setattr(tasks, "_notify_feishu_card_safe", fake_notify)

    await tasks.deliver_report_mail(log_id, [submission_id])

    async with AsyncSessionLocal() as db:
        row = await db.get(Submission, submission_id)
        assert row is not None
        assert row.status == "sent"
        assert row.needs_manual is False
        person = await db.get(Person, row.person_id)
        assert person is not None
        assert person.has_sent is True
        assert person.first_sent_at is not None
        assert person.last_sent_at is not None

        logs = (await db.scalars(select(MailLog))).all()
        assert any(log.id == log_id for log in logs)
