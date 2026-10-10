"""DeepSeek V4 Flash：判断提交信息是否为垃圾/虚假信息。"""

import json
import logging
import re

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是报告收集系统的数据质量审核助手。"
    "请判断用户提交的单位、职务、姓名、电话、邮箱是否为垃圾信息或明显虚假信息，"
    "例如：明显占位符（测试/张三/XXX）、乱码、广告推广、无意义内容、示例手机号/示例邮箱等。"
    "只输出一个 JSON 对象，不要输出解释、不要使用 Markdown 代码块。"
    "格式："
    '{"is_spam": true 或 false, "confidence": 0 到 1 的小数, '
    '"reason": "不超过 50 字的中文理由"}'
)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    cleaned = re.sub(r"```(?:json)?", "", text).strip("` \n")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


async def check_submission(
    *,
    organization: str,
    position: str,
    name: str,
    phone: str,
    email: str,
) -> dict:
    """返回 {flag, score, reason}。flag: ok / suspicious / error / skipped。"""

    if not settings.ai.enabled or not settings.ai.api_key or not settings.ai.base_url:
        return {"flag": "skipped", "score": None, "reason": None}

    user_content = "\n".join(
        [
            f"单位：{organization}",
            f"职务：{position}",
            f"姓名：{name}",
            f"电话：{phone}",
            f"邮箱：{email}",
        ]
    )
    payload = {
        "model": settings.ai.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "max_tokens": settings.ai.max_tokens,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.ai.timeout_seconds) as client:
            response = await client.post(
                f"{settings.ai.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.ai.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        parsed = _extract_json(content)
        if not parsed:
            raise ValueError(f"模型未返回可解析的 JSON：{content[:120]}")

        is_spam = bool(parsed.get("is_spam"))
        try:
            score = float(parsed.get("confidence"))
        except (TypeError, ValueError):
            score = None
        reason = str(parsed.get("reason") or "").strip()[:500] or None

        return {
            "flag": "suspicious" if is_spam else "ok",
            "score": score,
            "reason": reason,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI 判定失败：%s", exc)
        return {"flag": "error", "score": None, "reason": str(exc)[:500]}
