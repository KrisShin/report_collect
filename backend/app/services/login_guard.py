"""管理端登录失败锁定：Redis 计数或进程内降级。"""

import logging
import time

from app.core import redis as redis_module
from app.core.config import settings

logger = logging.getLogger(__name__)

_memory: dict[str, tuple[int, float]] = {}


async def is_locked(identity: str) -> int:
    """返回剩余锁定秒数，0 表示未锁定。"""

    client = redis_module.get_redis()
    if client is not None:
        try:
            ttl = await client.ttl(redis_module.key(f"login:lock:{identity}"))
            return max(int(ttl), 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis 查询登录锁定失败，降级进程内：%s", exc)

    item = _memory.get(identity)
    if not item:
        return 0
    count, until = item
    remaining = int(until - time.monotonic())
    if remaining <= 0:
        _memory.pop(identity, None)
        return 0
    return remaining if count >= settings.security.login_max_failures else 0


async def record_failure(identity: str) -> int:
    """记录一次失败，达到阈值后锁定。返回剩余锁定秒数。"""

    lock_seconds = settings.security.login_lock_seconds
    client = redis_module.get_redis()
    if client is not None:
        try:
            fail_key = redis_module.key(f"login:fail:{identity}")
            count = await client.incr(fail_key)
            await client.expire(fail_key, lock_seconds)
            if count >= settings.security.login_max_failures:
                await client.set(redis_module.key(f"login:lock:{identity}"), "1", ex=lock_seconds)
                await client.delete(fail_key)
                return lock_seconds
            return 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis 记录登录失败异常，降级进程内：%s", exc)

    count, _until = _memory.get(identity, (0, 0.0))
    count += 1
    if count >= settings.security.login_max_failures:
        _memory[identity] = (count, time.monotonic() + lock_seconds)
        return lock_seconds
    _memory[identity] = (count, time.monotonic() + lock_seconds)
    return 0


async def clear(identity: str) -> None:
    client = redis_module.get_redis()
    if client is not None:
        try:
            await client.delete(
                redis_module.key(f"login:fail:{identity}"),
                redis_module.key(f"login:lock:{identity}"),
            )
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis 清除登录失败记录异常：%s", exc)
    _memory.pop(identity, None)


def reset_memory() -> None:
    _memory.clear()
