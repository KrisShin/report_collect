import json

import fakeredis.aioredis
from fastapi import BackgroundTasks

from app.core import redis as redis_module
from app.core.config import settings
from app.services.jobs import enqueue
from app.worker import handle_message


async def test_enqueue_falls_back_to_background_tasks():
    background = BackgroundTasks()
    mode = await enqueue(background, "submission_process", submission_id=999999)
    assert mode == "inline"
    assert len(background.tasks) == 1
    assert background.tasks[0].func.__name__ == "process_submission"


async def test_enqueue_uses_redis_queue(monkeypatch):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_module, "_client", fake)
    monkeypatch.setattr(settings.redis, "enabled", True)

    mode = await enqueue(BackgroundTasks(), "report_mail", log_id=1, submission_ids=[1, 2])
    assert mode == "redis"

    raw = await fake.lindex(redis_module.key("jobs"), 0)
    message = json.loads(raw)
    assert message["job"] == "report_mail"
    assert message["payload"] == {"log_id": 1, "submission_ids": [1, 2]}


async def test_worker_handles_unknown_and_broken_messages():
    await handle_message("not-a-json")
    await handle_message(json.dumps({"job": "not_exist", "payload": {}}))
    # 提交不存在时任务应安全退出，不抛异常
    await handle_message(json.dumps({"job": "submission_process", "payload": {"submission_id": 0}}))
