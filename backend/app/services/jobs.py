"""任务入队：

- Redis 可用：LPUSH 到任务队列，由 `python -m app.worker` 独立进程消费（服务重启不丢任务）
- Redis 不可用：退回 FastAPI BackgroundTasks，本地开发零依赖
"""

import json
import logging
from datetime import UTC, datetime

from fastapi import BackgroundTasks

from app.core import redis as redis_module
from app.services.tasks import HANDLERS

logger = logging.getLogger(__name__)


async def enqueue(background: BackgroundTasks, job: str, **payload) -> str:
    """入队并返回执行方式：redis / inline。"""

    if job not in HANDLERS:
        raise ValueError(f"未知任务类型：{job}")

    client = redis_module.get_redis()
    if client is not None:
        try:
            message = json.dumps(
                {
                    "job": job,
                    "payload": payload,
                    "enqueued_at": datetime.now(UTC).isoformat(),
                },
                ensure_ascii=False,
            )
            await client.lpush(redis_module.key("jobs"), message)
            logger.info("任务已入队 Redis job=%s payload=%s", job, payload)
            return "redis"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis 入队失败，降级为进程内任务：%s", exc)

    background.add_task(HANDLERS[job], **payload)
    return "inline"
