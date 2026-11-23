"""任务入队：

- Redis 可用：LPUSH 到任务队列，由 `python -m app.worker` 独立进程消费（服务重启不丢任务）
- Redis 不可用：退回 FastAPI BackgroundTasks，本地开发零依赖
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from fastapi import BackgroundTasks

from app.core import redis as redis_module
from app.services.tasks import HANDLERS

logger = logging.getLogger(__name__)

# 持有后台 asyncio 任务的强引用，避免任务执行前被垃圾回收
_background_tasks: set[asyncio.Task] = set()


def _finish_background_task(task: asyncio.Task, job: str) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("后台任务执行失败 job=%s error=%s", job, exc, exc_info=exc)


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


async def enqueue_detached(job: str, **payload) -> str:
    """在后台任务内部继续投递后续任务（此处没有 BackgroundTasks 可用）。

    Redis 可用时仍写入持久队列；否则创建 asyncio 任务，与进程内降级语义一致。
    """

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
            logger.warning("Redis 入队失败，降级为异步任务：%s", exc)

    task = asyncio.create_task(HANDLERS[job](**payload))
    _background_tasks.add(task)
    task.add_done_callback(lambda finished: _finish_background_task(finished, job))
    return "task"
