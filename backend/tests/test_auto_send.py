"""已发送人员匹配后的自动发送 / 人工标记。"""

import json
from datetime import UTC, datetime, timedelta

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


async def _process_with_ai(
    monkeypatch,
    submission_id: int,
    *,
    ai_flag: str,
    detached: list[dict],
    texts: list[str],
) -> None:
    """以可控 AI 结果执行 process_submission，并捕获自动发送与飞书通知。"""

    async def fake_check(**_kwargs) -> dict:
        return {"flag": ai_flag, "score": 0.9, "reason": "测试判定"}

    async def fake_detached(job: str, **payload) -> str:
        detached.append({"job": job, **payload})
        return "task"

    async def fake_send_text(text: str, chat_id: str | None = None) -> dict:
        texts.append(text)
        return {}

    monkeypatch.setattr(tasks, "check_submission", fake_check)
    monkeypatch.setattr("app.services.jobs.enqueue_detached", fake_detached)
    monkeypatch.setattr(tasks.feishu_client, "send_text", fake_send_text)

    await tasks.process_submission(submission_id)


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
    assert [item["job"] for item in queued] == ["submission_process"]

    detached: list[dict] = []
    texts: list[str] = []
    await _process_with_ai(
        monkeypatch, second_id, ai_flag="ok", detached=detached, texts=texts
    )

    assert len(detached) == 1
    assert detached[0]["job"] == "report_mail"
    assert detached[0]["submission_ids"] == [second_id]

    async with AsyncSessionLocal() as db:
        row = await db.get(Submission, second_id)
        assert row is not None
        assert row.send_mode == "auto"
        assert row.needs_manual is False

        log = await db.get(MailLog, detached[0]["log_id"])
        assert log is not None
        assert log.recipient == BASE_PERSON["email"]
        assert log.subject == default_subject("报告 B")
        assert json.loads(log.submission_ids) == [second_id]

    assert "状态：已自动发送" in texts[-1]


async def test_suspicious_ai_blocks_auto_send(client, admin_client, monkeypatch):
    report_a = await create_report(admin_client, "报告 A")
    report_b = await create_report(admin_client, "报告 B")

    first = await submit(client, report_a, BASE_PERSON)
    assert first.status_code == 201
    await _mark_submission_sent(first.json()["id"])

    async def fake_enqueue(_background, job: str, **payload) -> str:
        return "inline"

    monkeypatch.setattr(routes_client, "enqueue", fake_enqueue)

    second = await submit(client, report_b, BASE_PERSON)
    assert second.status_code == 201
    second_id = second.json()["id"]

    detached: list[dict] = []
    texts: list[str] = []
    await _process_with_ai(
        monkeypatch, second_id, ai_flag="suspicious", detached=detached, texts=texts
    )

    assert detached == []
    async with AsyncSessionLocal() as db:
        row = await db.get(Submission, second_id)
        assert row is not None
        assert row.send_mode == "auto"
        assert row.ai_flag == "suspicious"
        assert row.needs_manual is True
        assert row.status == "pending"
        assert (await db.scalars(select(MailLog))).all() == []

    assert "状态：AI识别可疑，已拦截自动发送" in texts[-1]


async def test_auto_send_failure_requires_manual(client, admin_client, monkeypatch):
    report_a = await create_report(admin_client, "报告 A")
    report_b = await create_report(admin_client, "报告 B")

    first = await submit(client, report_a, BASE_PERSON)
    assert first.status_code == 201
    await _mark_submission_sent(first.json()["id"])

    async def fake_enqueue(_background, job: str, **payload) -> str:
        return "inline"

    monkeypatch.setattr(routes_client, "enqueue", fake_enqueue)

    second = await submit(client, report_b, BASE_PERSON)
    assert second.status_code == 201
    second_id = second.json()["id"]

    detached: list[dict] = []
    texts: list[str] = []
    await _process_with_ai(
        monkeypatch, second_id, ai_flag="ok", detached=detached, texts=texts
    )
    log_id = detached[0]["log_id"]

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


async def test_manual_send_ignores_suspicious_ai(client, admin_client, monkeypatch):
    report_id = await create_report(admin_client, "报告 D")
    response = await submit(client, report_id, BASE_PERSON)
    assert response.status_code == 201
    submission_id = response.json()["id"]

    async with AsyncSessionLocal() as db:
        row = await db.get(Submission, submission_id)
        assert row is not None
        row.ai_flag = "suspicious"
        row.ai_reason = "占位数据"
        await db.commit()

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


async def test_recent_unsent_filter_excludes_suspicious_and_old(
    client, admin_client
):
    report_id = await create_report(admin_client, "报告 E")

    def person(index: int) -> dict:
        return {
            "organization": "测试单位",
            "position": "测试职务",
            "name": f"用户{index}",
            "phone": f"13800138{index:03d}",
            "email": f"user{index}@example.com",
        }

    recent = await submit(client, report_id, person(1))
    suspicious = await submit(client, report_id, person(2))
    old = await submit(client, report_id, person(3))
    sent = await submit(client, report_id, person(4))
    assert (
        recent.status_code
        == suspicious.status_code
        == old.status_code
        == sent.status_code
        == 201
    )

    async with AsyncSessionLocal() as db:
        recent_row = await db.get(Submission, recent.json()["id"])
        assert recent_row is not None
        recent_row.ai_flag = None

        suspicious_row = await db.get(Submission, suspicious.json()["id"])
        assert suspicious_row is not None
        suspicious_row.ai_flag = "suspicious"

        old_row = await db.get(Submission, old.json()["id"])
        assert old_row is not None
        old_row.submitted_at = datetime.now(UTC) - timedelta(hours=4)

        sent_row = await db.get(Submission, sent.json()["id"])
        assert sent_row is not None
        sent_row.mail_sent_at = datetime.now(UTC)
        sent_row.needs_manual = False
        sent_row.status = "sent"
        await db.commit()

    response = await admin_client.get(
        "/api/admin/submissions",
        params={
            "recent_hours": 3,
            "needs_manual": "true",
            "unsent": "true",
            "exclude_ai_flag": "suspicious",
            "sort_by": "submitted_at",
            "sort_order": "asc",
            "page": 1,
            "page_size": 100,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [recent.json()["id"]]


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
