"""JWT 注销黑名单：Redis 存储，未启用时进程内降级（带过期清理）。"""

import logging
import time

from app.core import redis as redis_module

logger = logging.getLogger(__name__)

_memory: dict[str, float] = {}


def _prune() -> None:
    now = time.monotonic()
    for token_id, expire_at in list(_memory.items()):
        if expire_at <= now:
            _memory.pop(token_id, None)


async def revoke(token_id: str, ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    client = redis_module.get_redis()
    if client is not None:
        try:
            await client.set(redis_module.key(f"jwt:revoked:{token_id}"), "1", ex=ttl_seconds)
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis 注销 token 异常，降级进程内：%s", exc)
    _memory[token_id] = time.monotonic() + ttl_seconds


async def is_revoked(token_id: str) -> bool:
    if not token_id:
        return False
    client = redis_module.get_redis()
    if client is not None:
        try:
            return bool(await client.exists(redis_module.key(f"jwt:revoked:{token_id}")))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis 查询 token 黑名单异常，降级进程内：%s", exc)
    _prune()
    return token_id in _memory


def reset_memory() -> None:
    _memory.clear()
