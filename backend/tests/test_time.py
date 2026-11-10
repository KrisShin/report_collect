from datetime import datetime
from types import SimpleNamespace

from app.core.time import format_local, to_api_utc
from app.services.tasks import build_submission_notification


def test_format_local_treats_naive_datetime_as_utc():
    assert format_local(datetime(2026, 11, 9, 2, 50)) == "2026-11-09 10:50"


def test_to_api_utc_marks_naive_datetime_as_utc():
    value = to_api_utc(datetime(2026, 11, 9, 2, 50))

    assert value is not None
    assert value.utcoffset().total_seconds() == 0


def test_feishu_notification_uses_shanghai_time():
    submission = SimpleNamespace(
        name="张三",
        organization="测试单位",
        position="研究员",
        phone="13800138000",
        email="zhangsan@example.com",
        submitted_at=datetime(2026, 11, 9, 2, 50),
    )

    text = build_submission_notification(submission, "测试报告")

    assert "提交时间：2026-11-09 10:50" in text
