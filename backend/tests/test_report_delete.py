"""报告删除：有提交时禁止，密码二次确认。"""

from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.audit_log import AuditLog

ADMIN_PASSWORD = "TestPassw0rd!23"


async def create_report(admin_client, title: str = "待删除报告") -> str:
    response = await admin_client.post("/api/admin/reports", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


async def delete_report(client, report_id: str, password: str = ADMIN_PASSWORD):
    return await client.request(
        "DELETE", f"/api/admin/reports/{report_id}", json={"password": password}
    )


async def test_delete_empty_report_with_uploaded_attachment(admin_client):
    report_id = await create_report(admin_client)
    uploaded = await admin_client.post(
        f"/api/admin/reports/{report_id}/attachments",
        files=[("files", ("a.pdf", b"x", "application/pdf"))],
    )
    assert uploaded.status_code == 200
    upload_dir = Path(settings.mail.upload_dir) / report_id
    assert upload_dir.is_dir()

    response = await delete_report(admin_client, report_id)
    assert response.status_code == 200
    assert response.json()["deleted_attachments"] == 1
    assert not upload_dir.exists()
    assert (
        await admin_client.get(f"/api/admin/reports/{report_id}")
    ).status_code == 404

    async with AsyncSessionLocal() as session:
        actions = (await session.scalars(select(AuditLog.action))).all()
    assert "report_delete" in actions


async def test_delete_report_wrong_password(admin_client):
    report_id = await create_report(admin_client)
    response = await delete_report(admin_client, report_id, password="wrong-password")
    assert response.status_code == 400
    assert response.json()["detail"] == "管理员密码错误"
    assert (
        await admin_client.get(f"/api/admin/reports/{report_id}")
    ).status_code == 200


async def test_delete_report_with_submissions_blocked(client, admin_client):
    report_id = await create_report(admin_client)
    submitted = await client.post(
        "/api/client/submissions",
        json={
            "report_id": report_id,
            "organization": "测试单位",
            "position": "测试职务",
            "name": "张三",
            "phone": "13800138000",
            "email": "zhangsan@example.com",
        },
    )
    assert submitted.status_code == 201

    response = await delete_report(admin_client, report_id)
    assert response.status_code == 409
    assert "提交记录" in response.json()["detail"]
    assert (
        await admin_client.get(f"/api/admin/reports/{report_id}")
    ).status_code == 200


async def test_delete_report_requires_admin(client):
    response = await client.request(
        "DELETE",
        f"/api/admin/reports/{'0' * 32}",
        json={"password": ADMIN_PASSWORD},
    )
    assert response.status_code == 401


async def test_delete_missing_report(admin_client):
    response = await delete_report(admin_client, "0" * 32)
    assert response.status_code == 404
