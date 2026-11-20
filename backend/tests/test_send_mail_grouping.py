"""一键发送邮件按报告分组：每个报告一条 MailLog 与正确主题。"""

from sqlalchemy import select

from app.api import routes_admin
from app.db.session import AsyncSessionLocal
from app.models.mail_log import MailLog
from app.services.email_template import default_subject


async def create_report(admin_client, title: str, subject: str | None = None) -> str:
    payload: dict = {"title": title}
    if subject is not None:
        payload["email_subject"] = subject
    response = await admin_client.post("/api/admin/reports", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


async def submit(client, report_id: str, phone: str, email: str, name: str) -> int:
    response = await client.post(
        "/api/client/submissions",
        json={
            "report_id": report_id,
            "organization": "测试单位",
            "position": "测试职务",
            "name": name,
            "phone": phone,
            "email": email,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_send_mail_groups_by_report(client, admin_client, monkeypatch):
    report_a = await create_report(admin_client, "报告 A", "主题 A")
    report_b = await create_report(admin_client, "报告 B")
    id_a = await submit(client, report_a, "13800138001", "a@example.com", "甲")
    id_b = await submit(client, report_b, "13800138002", "b@example.com", "乙")

    queued: list[dict] = []

    async def fake_enqueue(_background, job: str, **payload) -> str:
        queued.append({"job": job, **payload})
        return "inline"

    monkeypatch.setattr(routes_admin, "enqueue", fake_enqueue)

    response = await admin_client.post(
        "/api/admin/submissions/send-mail", json={"ids": [id_a, id_b]}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert len(body["log_ids"]) == 2
    assert len(queued) == 2
    assert all(item["job"] == "report_mail" for item in queued)

    subjects = {group["report_id"]: group["subject"] for group in body["groups"]}
    assert subjects[report_a] == "主题 A"
    assert subjects[report_b] == default_subject("报告 B")

    async with AsyncSessionLocal() as session:
        logs = (await session.scalars(select(MailLog).order_by(MailLog.id))).all()
    assert sorted(log.subject for log in logs) == sorted(
        ["主题 A", default_subject("报告 B")]
    )
    assert all(log.status == "pending" for log in logs)
