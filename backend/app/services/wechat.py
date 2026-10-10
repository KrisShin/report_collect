"""微信浏览器识别（方案 A：不做网页授权，仅校验 UA）。"""

MICROMESSENGER_TOKEN = "micromessenger"


def is_wechat_browser(user_agent: str | None) -> bool:
    """判断 UA 是否来自微信内置浏览器。注意：UA 可伪造，仅作为访问体验限制。"""

    return MICROMESSENGER_TOKEN in (user_agent or "").lower()
