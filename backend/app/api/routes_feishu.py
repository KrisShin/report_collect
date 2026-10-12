"""飞书事件/卡片回调入口。

开放平台"卡片请求地址"：https://report.toputils.top/api/feishu/card/callback

安全说明：
- URL 验证（url_verification）是握手请求，飞书**不一定**带签名头，
  因此只校验 verification_token（与开放平台一致）。
- 真正的卡片动作回调：若配置了 encrypt_key，则强制校验 X-Lark-Signature；
  同时还要通过 verification_token 与来源群 chat_id 两道校验。
- 若开启加密套件，载荷是 AES-256-CBC 加密的 encrypt 字段，先解密再处理。
"""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request

from app.core.config import settings
from app.services.feishu_callback import (
    FeishuCallbackError,
    decrypt_payload,
    dispatcher,
    verify_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feishu", tags=["feishu"])


def _lark_header_names(request: Request) -> list[str]:
    return [name for name in request.headers if name.lower().startswith("x-lark")]


@router.post("/card/callback")
async def feishu_card_callback(request: Request, background: BackgroundTasks) -> dict:
    raw_body = await request.body()

    try:
        body = json.loads(raw_body or b"{}")
    except json.JSONDecodeError:
        return {"status": "failed", "msg": "invalid json"}

    # 1) 加密载荷先解密（AES-256-CBC）
    if "encrypt" in body:
        try:
            body = decrypt_payload(body["encrypt"], settings.feishu.encrypt_key)
        except (FeishuCallbackError, ValueError, KeyError, TypeError) as exc:
            logger.warning("飞书回调解密失败：%s", exc)
            return {"status": "failed", "msg": "decrypt failed"}

    # 2) URL 验证（握手）：只校验 verification_token
    if body.get("type") == "url_verification":
        return await dispatcher.dispatch(body, background)

    # 3) 卡片动作：配置了 encrypt_key 时必须验签
    if settings.feishu.encrypt_key:
        signature_ok = verify_signature(
            request.headers.get("X-Lark-Request-Timestamp", ""),
            request.headers.get("X-Lark-Request-Nonce", ""),
            raw_body,
            request.headers.get("X-Lark-Signature", ""),
        )
        if not signature_ok:
            logger.warning("飞书回调签名校验失败，Lark 头=%s", _lark_header_names(request))
            return {"status": "failed", "msg": "invalid signature"}

    return await dispatcher.dispatch(body, background)
