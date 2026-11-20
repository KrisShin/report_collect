"""报告邮件模板/附件上传与全局导入接口。"""

from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.services.attachments import collect_attachments
from app.services.email_template import HTML_TEMPLATE_NAME, TEMPLATE_DIR


async def create_report(admin_client, title: str = "邮件资产测试") -> str:
    response = await admin_client.post("/api/admin/reports", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


async def test_email_subject_create_update_and_clear(admin_client):
    response = await admin_client.post(
        "/api/admin/reports",
        json={"title": "主题测试", "email_subject": "  自定义主题  "},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email_subject"] == "自定义主题"
    assert body["has_email_template"] is False

    report_id = body["id"]
    listed = await admin_client.get("/api/admin/reports")
    row = next(item for item in listed.json() if item["id"] == report_id)
    assert row["email_subject"] == "自定义主题"

    cleared = await admin_client.patch(
        f"/api/admin/reports/{report_id}", json={"email_subject": ""}
    )
    assert cleared.status_code == 200
    assert cleared.json()["email_subject"] is None


async def test_template_upload_get_replace_delete(admin_client):
    report_id = await create_report(admin_client)
    first = "<html><body><p>第一版</p></body></html>"
    uploaded = await admin_client.post(
        f"/api/admin/reports/{report_id}/email-template",
        files={"file": ("v1.html", first.encode("utf-8"), "text/html")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["has_email_template"] is True
    assert uploaded.json()["name"] == "v1.html"

    fetched = await admin_client.get(f"/api/admin/reports/{report_id}/email-template")
    assert fetched.status_code == 200
    assert fetched.json()["html"] == first
    assert fetched.json()["name"] == "v1.html"

    second = "<html><body><p>第二版</p></body></html>"
    replaced = await admin_client.post(
        f"/api/admin/reports/{report_id}/email-template",
        files={"file": ("v2.html", second.encode("utf-8"), "text/html")},
    )
    assert replaced.status_code == 200
    fetched = await admin_client.get(f"/api/admin/reports/{report_id}/email-template")
    assert fetched.json()["html"] == second

    deleted = await admin_client.delete(
        f"/api/admin/reports/{report_id}/email-template"
    )
    assert deleted.status_code == 200
    assert deleted.json()["has_email_template"] is False
    missing = await admin_client.get(f"/api/admin/reports/{report_id}/email-template")
    assert missing.status_code == 404

    async with AsyncSessionLocal() as session:
        actions = (await session.scalars(select(AuditLog.action))).all()
    assert "report_template_upload" in actions
    assert "report_template_delete" in actions


async def test_template_rejects_invalid_files(admin_client, monkeypatch):
    report_id = await create_report(admin_client)
    valid = "<html><body><p>有效模板</p></body></html>"
    ok = await admin_client.post(
        f"/api/admin/reports/{report_id}/email-template",
        files={"file": ("ok.html", valid.encode("utf-8"), "text/html")},
    )
    assert ok.status_code == 200

    wrong_ext = await admin_client.post(
        f"/api/admin/reports/{report_id}/email-template",
        files={"file": ("bad.txt", b"plain", "text/plain")},
    )
    assert wrong_ext.status_code == 422

    bad_encoding = await admin_client.post(
        f"/api/admin/reports/{report_id}/email-template",
        files={"file": ("bad.html", b"\xff\xfe\x00", "text/html")},
    )
    assert bad_encoding.status_code == 422

    empty = await admin_client.post(
        f"/api/admin/reports/{report_id}/email-template",
        files={"file": ("empty.html", b"", "text/html")},
    )
    assert empty.status_code == 422

    monkeypatch.setattr(settings.mail, "max_template_kb", 0)
    too_large = await admin_client.post(
        f"/api/admin/reports/{report_id}/email-template",
        files={"file": ("big.html", b"<html>x</html>", "text/html")},
    )
    assert too_large.status_code == 413

    # 失败不覆盖旧模板
    fetched = await admin_client.get(f"/api/admin/reports/{report_id}/email-template")
    assert fetched.json()["html"] == valid


async def test_attachment_upload_list_delete_and_overwrite(admin_client):
    report_id = await create_report(admin_client)
    xlsx_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    uploaded = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments",
        files=[
            ("files", ("a.pdf", b"%PDF-1.4 first", "application/pdf")),
            ("files", ("b.xlsx", b"PK\x03\x04 data", xlsx_type)),
        ],
    )
    assert uploaded.status_code == 200
    body = uploaded.json()
    assert body["total"] == 2
    assert sorted(body["uploaded"]) == ["a.pdf", "b.xlsx"]

    listed = await admin_client.get(f"/api/admin/reports/{report_id}/attachments")
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert listed.json()["uses_legacy"] is False

    reports = await admin_client.get("/api/admin/reports")
    row = next(item for item in reports.json() if item["id"] == report_id)
    assert row["attachment_count"] == 2

    overwritten = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments",
        files=[("files", ("a.pdf", b"%PDF-1.4 second", "application/pdf"))],
    )
    assert overwritten.status_code == 200
    assert overwritten.json()["total"] == 2

    deleted = await admin_client.delete(
        f"/api/admin/reports/{report_id}/attachments/b.xlsx"
    )
    assert deleted.status_code == 200
    assert deleted.json()["remaining"] == 1

    missing = await admin_client.delete(
        f"/api/admin/reports/{report_id}/attachments/nope.pdf"
    )
    assert missing.status_code == 404


async def test_attachment_rejects_unsafe_files(admin_client, monkeypatch):
    report_id = await create_report(admin_client)

    bad_ext = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments",
        files=[("files", ("evil.exe", b"MZ", "application/octet-stream"))],
    )
    assert bad_ext.status_code == 422

    traversal = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments",
        files=[("files", ("../evil.pdf", b"x", "application/pdf"))],
    )
    assert traversal.status_code == 422

    hidden = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments",
        files=[("files", (".secret.pdf", b"x", "application/pdf"))],
    )
    assert hidden.status_code == 422

    empty = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments",
        files=[("files", ("empty.pdf", b"", "application/pdf"))],
    )
    assert empty.status_code == 422

    monkeypatch.setattr(settings.mail, "max_attachment_mb", 0)
    too_large = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments",
        files=[("files", ("big.pdf", b"x", "application/pdf"))],
    )
    assert too_large.status_code == 413
    monkeypatch.setattr(settings.mail, "max_attachment_mb", 20)

    monkeypatch.setattr(settings.mail, "max_upload_files", 1)
    too_many = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments",
        files=[
            ("files", ("one.pdf", b"1", "application/pdf")),
            ("files", ("two.pdf", b"2", "application/pdf")),
        ],
    )
    assert too_many.status_code == 422
    monkeypatch.setattr(settings.mail, "max_upload_files", 10)

    monkeypatch.setattr(settings.mail, "max_total_attachment_mb", 0)
    total_too_large = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments",
        files=[("files", ("total.pdf", b"x", "application/pdf"))],
    )
    assert total_too_large.status_code == 413

    listed = await admin_client.get(f"/api/admin/reports/{report_id}/attachments")
    assert listed.json()["total"] == 0


async def test_assets_require_admin(client):
    report_id = "0" * 32
    assert (
        await client.get(f"/api/admin/reports/{report_id}/attachments")
    ).status_code == 401
    assert (
        await client.get(f"/api/admin/reports/{report_id}/email-template")
    ).status_code == 401
    assert (
        await client.post(
            f"/api/admin/reports/{report_id}/attachments",
            files=[("files", ("a.pdf", b"x", "application/pdf"))],
        )
    ).status_code == 401


async def test_assets_report_not_found(admin_client):
    report_id = "0" * 32
    assert (
        await admin_client.get(f"/api/admin/reports/{report_id}/attachments")
    ).status_code == 404
    assert (
        await admin_client.get(f"/api/admin/reports/{report_id}/email-template")
    ).status_code == 404
    assert (
        await admin_client.post(
            f"/api/admin/reports/{report_id}/attachments",
            files=[("files", ("a.pdf", b"x", "application/pdf"))],
        )
    ).status_code == 404


async def test_import_global_template(admin_client):
    report_id = await create_report(admin_client)
    response = await admin_client.post(
        f"/api/admin/reports/{report_id}/email-template/import-global"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["has_email_template"] is True
    assert body["name"] == HTML_TEMPLATE_NAME
    assert body["size"] > 0

    fetched = await admin_client.get(f"/api/admin/reports/{report_id}/email-template")
    global_html = (TEMPLATE_DIR / HTML_TEMPLATE_NAME).read_text(encoding="utf-8")
    assert fetched.status_code == 200
    assert fetched.json()["html"] == global_html

    again = await admin_client.post(
        f"/api/admin/reports/{report_id}/email-template/import-global"
    )
    assert again.status_code == 409

    async with AsyncSessionLocal() as session:
        actions = (await session.scalars(select(AuditLog.action))).all()
    assert "report_template_import_global" in actions


async def test_import_global_attachments(admin_client, monkeypatch, tmp_path):
    report_id = await create_report(admin_client)
    legacy = tmp_path / "mail_attachments"
    legacy.mkdir()
    (legacy / "global.pdf").write_bytes(b"global")
    report_legacy = legacy / report_id
    report_legacy.mkdir()
    (report_legacy / "specific.pdf").write_bytes(b"specific")
    (report_legacy / ".hidden.pdf").write_bytes(b"hidden")

    monkeypatch.setattr(settings.mail, "attachment_dir", str(legacy))
    monkeypatch.setattr(settings.mail, "max_attachment_mb", 20)

    response = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments/import-global"
    )
    assert response.status_code == 200
    body = response.json()
    assert sorted(body["imported"]) == ["global.pdf", "specific.pdf"]
    assert body["total"] == 2

    # 发送侧看到的就是导入后的附件
    names = [name for name, _ in collect_attachments(report_id)]
    assert sorted(names) == ["global.pdf", "specific.pdf"]

    # 原全局文件保留
    assert (legacy / "global.pdf").read_bytes() == b"global"
    assert (report_legacy / "specific.pdf").read_bytes() == b"specific"

    again = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments/import-global"
    )
    assert again.status_code == 409

    async with AsyncSessionLocal() as session:
        actions = (await session.scalars(select(AuditLog.action))).all()
    assert "report_attachment_import_global" in actions


async def test_import_global_attachments_without_files(
    admin_client, monkeypatch, tmp_path
):
    report_id = await create_report(admin_client)
    empty = tmp_path / "empty_attachments"
    empty.mkdir()
    monkeypatch.setattr(settings.mail, "attachment_dir", str(empty))

    response = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments/import-global"
    )
    assert response.status_code == 404
