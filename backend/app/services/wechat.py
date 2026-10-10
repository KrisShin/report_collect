"""微信服务号网页授权。"""

from urllib.parse import urlencode

import httpx

from app.core.config import settings

AUTHORIZE_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
ACCESS_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"


class WeChatError(RuntimeError):
    pass


def build_authorize_url(state: str = "rc", scope: str = "snsapi_base") -> str:
    if not settings.wechat_app_id or not settings.wechat_oauth_redirect_uri:
        raise WeChatError("微信 AppID 或授权回调地址未配置")

    query = {
        "appid": settings.wechat_app_id,
        "redirect_uri": settings.wechat_oauth_redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(query)}#wechat_redirect"


async def exchange_code_for_openid(code: str) -> dict:
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise WeChatError("微信 AppID/AppSecret 未配置")

    params = {
        "appid": settings.wechat_app_id,
        "secret": settings.wechat_app_secret,
        "code": code,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(ACCESS_TOKEN_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("errcode"):
        raise WeChatError(f"微信授权失败: {data.get('errcode')} {data.get('errmsg')}")
    return data
