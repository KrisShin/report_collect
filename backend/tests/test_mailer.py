from app.core.config import settings
from app.services.mailer import OutgoingMail, send_mails


class _FakeSMTP:
    """模拟 SMTP：记录每次发送，第二次故意失败。"""

    instances = 0

    def __init__(self, **_kwargs) -> None:
        _FakeSMTP.instances += 1
        self.sent: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def login(self, _user: str, _password: str) -> None:
        return None

    async def send_message(self, message) -> None:  # noqa: ANN001
        self.sent.append(message["To"])
        if len(self.sent) == 2:
            raise RuntimeError("boom")


async def test_send_mails_gate_and_failure_isolation(monkeypatch):
    monkeypatch.setattr("app.services.mailer.aiosmtplib.SMTP", _FakeSMTP)
    monkeypatch.setattr(settings.mail, "user", "sender@example.com")
    monkeypatch.setattr(settings.mail, "password", "secret")
    monkeypatch.setattr(settings.mail, "send_interval_seconds", 0)

    _FakeSMTP.instances = 0
    mails = [
        OutgoingMail([f"user{i}@example.com"], "主题", "<p>hi</p>") for i in range(1, 4)
    ]
    errors = await send_mails(mails)

    # 单封失败不影响其他邮件
    assert errors == [None, "boom", None]
    # 整个批次只建立一条 SMTP 连接
    assert _FakeSMTP.instances == 1

async def test_send_mails_progress_callback(monkeypatch):
    monkeypatch.setattr("app.services.mailer.aiosmtplib.SMTP", _FakeSMTP)
    monkeypatch.setattr(settings.mail, "user", "sender@example.com")
    monkeypatch.setattr(settings.mail, "password", "secret")
    monkeypatch.setattr(settings.mail, "send_interval_seconds", 0)

    seen: list[tuple[int, int, int, int]] = []

    async def hook(done: int, total: int, success: int, failed: int) -> None:
        seen.append((done, total, success, failed))

    mails = [OutgoingMail([f"u{i}@example.com"], "主题", "<p>x</p>") for i in range(1, 4)]
    await send_mails(mails, on_progress=hook)

    # 第 2 封故意失败：进度回调仍按顺序上报，统计正确
    assert seen == [(1, 3, 1, 0), (2, 3, 1, 1), (3, 3, 2, 1)]


async def test_progress_reporter_throttle(monkeypatch):
    from app.services import tasks

    sent: list[str] = []

    async def fake_notify(text: str) -> None:
        sent.append(text)

    monkeypatch.setattr(tasks, "_notify_feishu_safe", fake_notify)

    never = tasks._MailProgressReporter(interval=999)
    await never(1, 10, 1, 0)
    assert sent == []

    always = tasks._MailProgressReporter(interval=0)
    await always(1, 10, 1, 0)
    await always(2, 10, 2, 0)
    assert len(sent) == 2
    assert "1/10" in sent[0]
    assert "2/10" in sent[1]

async def test_collect_attachments_from_static_dir(tmp_path, monkeypatch):
    from app.services.attachments import collect_attachments

    base = tmp_path / "mail_attachments"
    base.mkdir()
    (base / "通知.pdf").write_bytes(b"pdf-content")
    (base / ".hidden.tmp").write_bytes(b"x")

    report_dir = base / "report-1"
    report_dir.mkdir()
    (report_dir / "专属说明.docx").write_bytes(b"doc-content")

    monkeypatch.setattr(settings.mail, "attachment_dir", str(base))
    monkeypatch.setattr(settings.mail, "max_attachment_mb", 20)

    names = [name for name, _ in collect_attachments("report-1")]
    assert "通知.pdf" in names
    assert "专属说明.docx" in names
    assert ".hidden.tmp" not in names

    # 其他报告只拿到公共附件
    assert [name for name, _ in collect_attachments("report-2")] == ["通知.pdf"]

    # 超出大小上限时跳过
    monkeypatch.setattr(settings.mail, "max_attachment_mb", 0)
    assert collect_attachments("report-1") == []
