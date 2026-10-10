"""Redis 客户端（可选）。未启用或连接失败时返回 None，调用方自动降级。"""

import contextlib
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None


def get_redis():
    """返回 redis.asyncio 客户端；未启用或初始化失败返回 None。"""

    global _client
    if not settings.redis.enabled:
        return None

    if _client is None:
        try:
            from redis.asyncio import Redis

            _client = Redis.from_url(
                settings.redis.url,
                decode_responses=True,
                socket_timeout=settings.redis.socket_timeout,
                socket_connect_timeout=settings.redis.socket_timeout,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis 初始化失败，将降级为进程内实现：%s", exc)
            return None

    return _client


def key(name: str) -> str:
    return f"{settings.redis.key_prefix}:{name}"


async def ping() -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(await client.ping())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis ping 失败：%s", exc)
        return False


async def close() -> None:
    global _client
    if _client is not None:
        with contextlib.suppress(Exception):
            await _client.aclose()
        _client = None
