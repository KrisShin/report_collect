"""Redis 任务 worker。

生产环境单独启动（systemd 或 docker compose）：
    C:\\Users\\HP\\miniconda3\\envs\\reportc\\python.exe -m app.worker
"""

import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.core import redis as redis_module
from app.core.config import settings
from app.core.logging import setup_logging
from app.services.tasks import HANDLERS

logger = logging.getLogger("app.worker")

MAX_RETRY = 3


async def handle_message(raw: str) -> None:
    try:
        message = json.loads(raw)
        job = message["job"]
        payload = message.get("payload") or {}
    except Exception as exc:  # noqa: BLE001
        logger.error("无法解析任务消息：%s raw=%s", exc, raw[:300])
        return

    handler = HANDLERS.get(job)
    if handler is None:
        logger.error("未知任务类型 job=%s", job)
        return

    try:
        await handler(**payload)
        logger.info("任务执行完成 job=%s payload=%s", job, payload)
    except Exception:  # noqa: BLE001
        logger.exception("任务执行失败 job=%s payload=%s", job, payload)


async def main() -> None:
    setup_logging(settings.app.debug)
    client = redis_module.get_redis()
    if client is None:
        raise SystemExit("Redis 未启用或不可用，请检查 config.yaml 的 redis 配置")

    queue_key = redis_module.key(settings.redis.job_queue_key)
    logger.info("worker 已启动，监听队列 %s", queue_key)

    while True:
        try:
            # 阻塞时间必须小于 Redis socket_timeout（配置为 2s），否则会误报超时
            item = await client.brpop(queue_key, timeout=1)
            if item is None:
                continue
            _, raw = item
            await handle_message(raw)
        except (TimeoutError, aioredis.exceptions.TimeoutError):
            continue
        except asyncio.CancelledError:  # pragma: no cover
            break
        except Exception:  # noqa: BLE001
            logger.exception("worker 主循环异常，1 秒后重试")
            await asyncio.sleep(1)

    await redis_module.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("worker 已停止")
