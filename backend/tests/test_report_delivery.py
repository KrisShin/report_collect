"""投递时按报告使用自定义主题/模板/附件，未配置时回退全局内容。"""

from app.api import routes_admin
from app.core.config import settings
from app.services import tasks
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


async def test_delivery_uses_report_assets_and_falls_back(
    client, admin_client, monkeypatch, tmp_path
):
    report_a = await create_report(admin_client, "报告 A", "主题 A")
    report_b = await create_report(admin_client, "报告 B")
    id_a = await submit(client, report_a, "13800138011", "a@example.com", "甲")
    id_b = await submit(client, report_b, "13800138012", "b@example.com", "乙")

    custom_html = "<html><body><p>自定义 A</p><p>第二段</p></body></html>"
    uploaded = await admin_client.post(
        f"/api/admin/reports/{report_a}/email-template",
        files={"file": ("custom.html", custom_html.encode("utf-8"), "text/html")},
    )
    assert uploaded.status_code == 200
    uploaded = await admin_client.post(
        f"/api/admin/reports/{report_a}/attachments",
        files=[("files", ("a.pdf", b"custom-attachment", "application/pdf"))],
    )
    assert uploaded.status_code == 200

    # 报告 B 没有上传附件，回退旧全局目录
    legacy = tmp_path / "mail_attachments"
    legacy.mkdir()
    (legacy / "legacy.pdf").write_bytes(b"legacy-attachment")
    monkeypatch.setattr(settings.mail, "attachment_dir", str(legacy))
    monkeypatch.setattr(settings.mail, "max_attachment_mb", 20)

    # 捕获入队，避免接口返回后自动执行后台投递
    async def fake_enqueue(_background, job: str, **payload) -> str:
        return "inline"

    monkeypatch.setattr(routes_admin, "enqueue", fake_enqueue)

    response = await admin_client.post(
        "/api/admin/submissions/send-mail", json={"ids": [id_a, id_b]}
    )
    assert response.status_code == 200
    log_ids = {group["report_id"]: group["log_id"] for group in response.json()["groups"]}

    sent = []

    async def fake_send_mails(mails, **_kwargs):
        sent.extend(mails)
        return [None] * len(mails)

    async def fake_notify(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(tasks, "send_mails", fake_send_mails)
    monkeypatch.setattr(tasks, "_notify_feishu_safe", fake_notify)
    monkeypatch.setattr(tasks, "_notify_feishu_card_safe", fake_notify)

    await tasks.deliver_report_mail(log_ids[report_a], [id_a])
    mail_a = sent[-1]
    assert mail_a.subject == "主题 A"
    assert mail_a.html_body == custom_html
    assert mail_a.text_body == "自定义 A\n\n第二段"
    assert [name for name, _ in mail_a.extra_attachments] == ["a.pdf"]
    assert mail_a.extra_attachments[0][1] == b"custom-attachment"

    await tasks.deliver_report_mail(log_ids[report_b], [id_b])
    mail_b = sent[-1]
    assert mail_b.subject == default_subject("报告 B")
    assert "中国电动重卡补能基础设施进展报告" in mail_b.html_body
    assert mail_b.text_body.startswith("各位专家、行业同仁：")
    assert [name for name, _ in mail_b.extra_attachments] == ["legacy.pdf"]
