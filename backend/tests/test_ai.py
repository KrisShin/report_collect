import httpx
import respx

from app.core.config import settings
from app.services.ai import check_submission

SAMPLE = {
    "organization": "测试单位",
    "position": "测试",
    "name": "张三",
    "phone": "13800138000",
    "email": "zhangsan@example.com",
}


def _enable_ai(monkeypatch, base_url: str = "http://ai.test/v1") -> None:
    monkeypatch.setattr(settings.ai, "enabled", True)
    monkeypatch.setattr(settings.ai, "api_key", "test-key")
    monkeypatch.setattr(settings.ai, "base_url", base_url)


@respx.mock
async def test_check_submission_flags_spam(monkeypatch):
    _enable_ai(monkeypatch)
    respx.post("http://ai.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"is_spam": true, "confidence": 0.93, '
                                '"reason": "占位测试数据"}'
                            )
                        }
                    }
                ]
            },
        )
    )

    result = await check_submission(**SAMPLE)
    assert result["flag"] == "suspicious"
    assert result["score"] == 0.93
    assert result["reason"] == "占位测试数据"


@respx.mock
async def test_check_submission_flags_normal(monkeypatch):
    _enable_ai(monkeypatch)
    respx.post("http://ai.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '```json\n{"is_spam": false, "confidence": 0.88, '
                                '"reason": "信息正常"}\n```'
                            )
                        }
                    }
                ]
            },
        )
    )

    result = await check_submission(**SAMPLE)
    assert result["flag"] == "ok"
    assert result["score"] == 0.88


@respx.mock
async def test_check_submission_handles_gateway_error(monkeypatch):
    _enable_ai(monkeypatch)
    respx.post("http://ai.test/v1/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    result = await check_submission(**SAMPLE)
    assert result["flag"] == "error"
    assert result["reason"]


async def test_check_submission_skipped_when_disabled(monkeypatch):
    monkeypatch.setattr(settings.ai, "enabled", False)
    result = await check_submission(**SAMPLE)
    assert result["flag"] == "skipped"
