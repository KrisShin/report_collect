"""接口限流：Redis 计数（生产）或进程内滑动窗口（本地降级）。"""

import logging
import time
from collections import defaultdict, deque

from app.core import redis as redis_module

logger = logging.getLogger(__name__)

_memory: dict[str, deque[float]] = defaultdict(deque)


async def hit(name: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """记录一次请求，返回 (是否允许, 剩余次数)。"""

    if limit <= 0:
        return True, 0

    client = redis_module.get_redis()
    if client is not None:
        try:
            full_key = redis_module.key(f"rl:{name}")
            count = await client.incr(full_key)
            if count == 1:
                await client.expire(full_key, window_seconds)
            return count <= limit, max(limit - count, 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis 限流失败，降级为进程内限流：%s", exc)

    now = time.monotonic()
    bucket = _memory[name]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return False, 0
    bucket.append(now)
    return True, limit - len(bucket)


def reset_memory() -> None:
    """仅用于测试。"""

    _memory.clear()
