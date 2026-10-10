"""飞书机器人：tenant_access_token 缓存 + 群消息发送。"""

import json
import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class FeishuError(RuntimeError):
    pass


class FeishuClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.feishu_base_url).rstrip("/")
        self._token: str | None = None
        self._token_expire_at: float = 0

    async def get_tenant_access_token(self) -> str:
        now = time.monotonic()
        if self._token and now < self._token_expire_at:
            return self._token

        if not settings.feishu_app_id or not settings.feishu_app_secret:
            raise FeishuError("飞书 AppID/AppSecret 未配置")

        url = f"{self.base_url}/auth/v3/tenant_access_token/internal"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json={
                    "app_id": settings.feishu_app_id,
                    "app_secret": settings.feishu_app_secret,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            raise FeishuError(f"获取 tenant_access_token 失败: {data}")

        self._token = data["tenant_access_token"]
        # 提前 300 秒过期，避免边界失效
        self._token_expire_at = now + max(int(data.get("expire", 7200)) - 300, 60)
        return self._token

    async def send_text(self, text: str, chat_id: str | None = None) -> dict:
        receive_id = chat_id or settings.feishu_chat_id
        if not receive_id:
            raise FeishuError("飞书群 chat_id 未配置")

        token = await self.get_tenant_access_token()
        url = f"{self.base_url}/im/v1/messages?receive_id_type=chat_id"
        payload = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("code") != 0:
            raise FeishuError(f"发送飞书消息失败: {data}")

        logger.info("飞书提醒已发送 chat_id=%s", receive_id)
        return data


feishu_client = FeishuClient()
