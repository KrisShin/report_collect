import json

from app.core.config import settings
from app.services.feishu_callback import verify_signature

VERIFY_TOKEN = "verify-token-test"
CHAT_ID = "oc_admin_group"


def _action_body(log_id: int, chat_id: str = CHAT_ID, token: str = VERIFY_TOKEN) -> dict:
    return {
        "schema": "2.0",
        "header": {"token": token, "event_type": "card.action.trigger"},
        "event": {
            "operator": {"open_id": "ou_test_user"},
            "action": {
                "tag": "button",
                "value": {"action_type": "retry_mail", "log_id": log_id},
            },
            "context": {"open_chat_id": chat_id},
        },
    }


def test_verify_signature(monkeypatch):
    monkeypatch.setattr(settings.feishu, "encrypt_key", "ek_test")
    import hashlib

    raw = b'{"a":1}'
    ts, nonce = "1700000000", "abc"
    good = hashlib.sha256(ts.encode() + nonce.encode() + b"ek_test" + raw).hexdigest()

    assert verify_signature(ts, nonce, raw, good) is True
    assert verify_signature(ts, nonce, raw, "bad") is False
    assert verify_signature(ts, nonce, raw, "") is False

    # 未配置 encrypt_key 时跳过签名校验（依赖 token + 群校验）
    monkeypatch.setattr(settings.feishu, "encrypt_key", "")
    assert verify_signature(ts, nonce, raw, "") is True


async def test_url_verification(client, monkeypatch):
    monkeypatch.setattr(settings.feishu, "verification_token", VERIFY_TOKEN)

    ok = await client.post(
        "/api/feishu/card/callback",
        json={"type": "url_verification", "token": VERIFY_TOKEN, "challenge": "challenge-1"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"challenge": "challenge-1"}

    bad = await client.post(
        "/api/feishu/card/callback",
        json={"type": "url_verification", "token": "wrong", "challenge": "x"},
    )
    assert bad.json().get("status") == "failed"


async def test_callback_rejects_other_group(client, monkeypatch):
    monkeypatch.setattr(settings.feishu, "verification_token", VERIFY_TOKEN)
    monkeypatch.setattr(settings.feishu, "chat_id", CHAT_ID)

    response = await client.post(
        "/api/feishu/card/callback", json=_action_body(1, chat_id="oc_other")
    )
    assert response.json().get("status") == "failed"


async def test_retry_action_creates_retry_log(client, monkeypatch):
    from app.db.session import AsyncSessionLocal
    from app.models.mail_log import MailLog

    monkeypatch.setattr(settings.feishu, "verification_token", VERIFY_TOKEN)
    monkeypatch.setattr(settings.feishu, "chat_id", CHAT_ID)
    monkeypatch.setattr(settings.mail, "retry_delay_seconds", 0)

    async with AsyncSessionLocal() as session:
        log = MailLog(
            submission_ids="[999999]",
            failed_submission_ids="[999999]",
            recipient="nobody@example.com",
            subject="【报告收集】信息确认",
            status="partial",
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        log_id = log.id

    response = await client.post("/api/feishu/card/callback", json=_action_body(log_id))
    body = response.json()
    assert body["toast"]["type"] == "success"
    assert "重试任务已提交" in json.dumps(body, ensure_ascii=False)

    # 同一批 5 分钟内再次触发会被限流
    again = await client.post("/api/feishu/card/callback", json=_action_body(log_id))
    assert "过于频繁" in json.dumps(again.json(), ensure_ascii=False)


async def test_retry_action_missing_log(client, monkeypatch):
    monkeypatch.setattr(settings.feishu, "verification_token", VERIFY_TOKEN)
    monkeypatch.setattr(settings.feishu, "chat_id", CHAT_ID)

    response = await client.post("/api/feishu/card/callback", json=_action_body(123456))
    assert "记录不存在" in json.dumps(response.json(), ensure_ascii=False)
