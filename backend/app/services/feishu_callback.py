"""飞书卡片回调：URL 验证 / 解密 / 验签 / 动作分发。

飞书开放平台"卡片请求地址"填写：https://report.toputils.top/api/feishu/card/callback
安全防线（三道）：
1. verification_token 必须与开放平台一致
2. 来源群 open_chat_id 必须是指定管理群
3. 若配置了 encrypt_key，则校验 X-Lark-Signature 并对 encrypt 载荷解密
"""

import base64
import hashlib
import hmac
import json
import logging
from typing import Any

from Crypto.Cipher import AES
from fastapi import BackgroundTasks
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.mail_log import MailLog
from app.services.jobs import enqueue
from app.services.rate_limit import hit

logger = logging.getLogger(__name__)

RETRY_PER_LOG_SECONDS = 300


class FeishuCallbackError(RuntimeError):
    pass


def decrypt_payload(encrypted: str, encrypt_key: str) -> dict:
    """解密飞书 encrypt 载荷（AES-256-CBC，PKCS7）。"""

    if not encrypt_key:
        raise FeishuCallbackError("收到加密回调，但未配置 feishu.encrypt_key")

    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    data = base64.b64decode(encrypted)
    iv, cipher_text = data[:16], data[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plain = cipher.decrypt(cipher_text)
    pad = plain[-1]
    if not 1 <= pad <= 16:
        raise FeishuCallbackError("解密后填充非法")
    return json.loads(plain[:-pad].decode("utf-8"))


def verify_signature(timestamp: str, nonce: str, raw_body: bytes, signature: str) -> bool:
    """校验 X-Lark-Signature：sha256(timestamp + nonce + encrypt_key + body)。"""

    encrypt_key = settings.feishu.encrypt_key
    if not encrypt_key:
        # 未启用加密套件时依赖 verification_token + 群校验
        return True
    if not signature:
        return False
    expected = hashlib.sha256(
        timestamp.encode("utf-8") + nonce.encode("utf-8") + encrypt_key.encode("utf-8") + raw_body
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def build_card(
    title: str,
    content: str,
    toast: tuple[str, str] = ("success", "操作成功"),
    template: str = "grey",
) -> dict:
    """卡片回调的标准响应：toast + 原位更新卡片。"""

    return {
        "toast": {"type": toast[0], "content": toast[1]},
        "card": {
            "type": "raw",
            "data": {
                "config": {"wide_screen_mode": True, "update_multi": True},
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": template,
                },
                "elements": [
                    {"tag": "hr"},
                    {"tag": "div", "text": {"tag": "lark_md", "content": content}},
                ],
            },
        },
    }


class FeishuCardDispatcher:
    """卡片动作分发器：action_type -> handler。"""

    def __init__(self) -> None:
        self.handlers = {
            "retry_mail": self.handle_retry_mail,
        }

    async def dispatch(self, body: dict, background: BackgroundTasks) -> dict:
        # 1) URL 验证（配置回调地址时飞书会先请求一次）
        if body.get("type") == "url_verification":
            if body.get("token") != settings.feishu.verification_token:
                logger.warning("飞书 URL 验证失败：verification_token 不匹配")
                return {"status": "failed", "msg": "invalid verification token"}
            return {"challenge": body.get("challenge")}

        # 2) 安全校验：token + 来源群
        header = body.get("header") or {}
        event = body.get("event") or {}
        req_token = header.get("token") or event.get("token")
        chat_id = (event.get("context") or {}).get("open_chat_id")

        if req_token != settings.feishu.verification_token or chat_id != settings.feishu.chat_id:
            logger.warning(
                "拦截非法飞书回调：token_ok=%s chat_id=%s",
                req_token == settings.feishu.verification_token,
                chat_id,
            )
            return {"status": "failed", "msg": "access denied"}

        # 3) 分发
        value = (event.get("action") or {}).get("value") or {}
        action_type = value.get("action_type")
        handler = self.handlers.get(action_type) if action_type else None
        if handler is None:
            logger.warning("未知的飞书卡片动作：%s", action_type)
            return {"status": "success"}

        operator = (event.get("operator") or {}).get("open_id")
        logger.info("飞书卡片动作=%s operator=%s value=%s", action_type, operator, value)
        return await handler(value, operator, background)

    async def handle_retry_mail(
        self, value: dict[str, Any], operator: str | None, background: BackgroundTasks
    ) -> dict:
        try:
            log_id = int(value.get("log_id") or 0)
        except (TypeError, ValueError):
            log_id = 0
        if not log_id:
            return build_card(
                "⛔ 参数错误",
                "缺少 log_id，无法重试。",
                ("error", "参数错误"),
                "red",
            )

        allowed, _remaining = await hit(
            f"mailretry:log:{log_id}", 1, RETRY_PER_LOG_SECONDS
        )
        if not allowed:
            return build_card(
                "⏳ 操作过于频繁",
                "同一批失败邮件 5 分钟内只能触发一次重试。",
                ("warning", "请稍后再试"),
                "orange",
            )

        async with AsyncSessionLocal() as db:
            log = await db.get(MailLog, log_id)
            if log is None:
                return build_card(
                    "⛔ 记录不存在",
                    f"找不到 mail_log {log_id}。",
                    ("error", "记录不存在"),
                    "red",
                )

            try:
                failed_ids = [
                    int(item) for item in json.loads(log.failed_submission_ids or "[]")
                ]
            except (TypeError, ValueError):
                failed_ids = []

            if not failed_ids:
                return build_card(
                    "✅ 无需重试",
                    "本次发送没有失败的邮件。",
                    ("success", "无需重试"),
                    "green",
                )

            pending = await db.scalar(
                select(MailLog.id)
                .where(MailLog.retry_of == log_id)
                .where(MailLog.status == "pending")
                .limit(1)
            )
            if pending:
                return build_card(
                    "⏳ 重试已在进行",
                    "该批失败邮件已经提交过重试，请勿重复点击。",
                    ("warning", "请勿重复操作"),
                    "orange",
                )

            retry_log = MailLog(
                submission_ids=json.dumps(failed_ids),
                failed_submission_ids="[]",
                retry_of=log_id,
                recipient=log.recipient,
                subject=log.subject,
                status="pending",
            )
            db.add(retry_log)
            await db.commit()
            await db.refresh(retry_log)
            retry_log_id = retry_log.id

        await enqueue(
            background,
            "report_mail_retry",
            log_id=retry_log_id,
            submission_ids=failed_ids,
        )
        logger.info(
            "飞书回调触发重试 operator=%s log_id=%s retry_log=%s count=%s",
            operator,
            log_id,
            retry_log_id,
            len(failed_ids),
        )
        return build_card(
            "✅ 重试任务已提交",
            f"将在 **5 分钟** 后重试这 {len(failed_ids)} 封失败的邮件，完成后会再次汇报。",
            ("success", "已提交重试"),
            "green",
        )


dispatcher = FeishuCardDispatcher()
