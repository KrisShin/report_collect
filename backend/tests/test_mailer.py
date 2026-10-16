from app.core.config import settings
from app.services.mailer import OutgoingMail, send_mails


class _FakeSMTP:
    """模拟 SMTP：记录每次发送，第二次故意失败。"""

    instances = 0
    sent_to: list[str] = []

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
        type(self).sent_to.append(message["To"])
        if len(self.sent) == 2:
            raise RuntimeError("boom")


async def test_send_mails_gate_and_failure_isolation(monkeypatch):
    monkeypatch.setattr("app.services.mailer.aiosmtplib.SMTP", _FakeSMTP)
    monkeypatch.setattr(settings.mail, "user", "sender@example.com")
    monkeypatch.setattr(settings.mail, "password", "secret")
    monkeypatch.setattr(settings.mail, "send_interval_seconds", 0)

    _FakeSMTP.instances = 0
    _FakeSMTP.sent_to = []
    mails = [
        OutgoingMail([f"user{i}@example.com"], "主题", "<p>hi</p>") for i in range(1, 4)
    ]
    errors = await send_mails(mails)

    # 单封失败不影响其他邮件
    assert errors == [None, "boom", None]
    # 整个批次只建立一条 SMTP 连接
    assert _FakeSMTP.instances == 1
    # 测试门控已取消：按调用方传入的真实收件人发送
    assert _FakeSMTP.sent_to == [
        "user1@example.com",
        "user2@example.com",
        "user3@example.com",
    ]

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


async def test_deliver_report_mail_reads_attachments_once(monkeypatch):
    """群发时附件只读一次盘，且每封邮件复用同一份 bytes（避免 N 倍内存）。"""
    from app.services import tasks

    shared = [("进展报告.pdf", b"x" * 1024)]
    reads: list[str | None] = []
    batch: list[OutgoingMail] = []

    def fake_collect(report_id: str | None = None) -> list[tuple[str, bytes]]:
        reads.append(report_id)
        return shared

    async def fake_send_mails(mails: list[OutgoingMail], **_kwargs) -> list[None]:
        batch.extend(mails)
        return [None] * len(mails)

    async def fake_titles(_db) -> dict[str, str]:
        return {}

    async def fake_notify(*_args, **_kwargs) -> None:
        return None

    class _FakeLog:
        subject = "【报告收集】信息确认"
        status = "pending"
        error = None
        attachment_name = None
        failed_submission_ids = None
        sent_at = None

    class _FakeRow:
        def __init__(self, index: int) -> None:
            self.id = index
            self.email = f"u{index}@example.com"
            self.report_id = "a" * 32
            self.report_title = None
            self.status = "pending"
            self.mail_sent_at = None
            self.mail_error = None
            self.is_processed = False
            self.processed_at = None
            self.processed_action = None

    rows = [_FakeRow(index) for index in (1, 2, 3)]

    class _FakeResult:
        def all(self) -> list[_FakeRow]:
            return rows

    class _FakeDb:
        async def get(self, *_args) -> _FakeLog:
            return _FakeLog()

        async def scalars(self, *_args) -> _FakeResult:
            return _FakeResult()

        async def commit(self) -> None:
            return None

    class _FakeSession:
        async def __aenter__(self) -> _FakeDb:
            return _FakeDb()

        async def __aexit__(self, *_exc) -> bool:
            return False

    monkeypatch.setattr(tasks, "AsyncSessionLocal", _FakeSession)
    monkeypatch.setattr(tasks, "collect_attachments", fake_collect)
    monkeypatch.setattr(tasks, "send_mails", fake_send_mails)
    monkeypatch.setattr(tasks, "render_report_email", lambda **_kwargs: "<p>x</p>")
    monkeypatch.setattr(tasks, "_report_titles", fake_titles)
    monkeypatch.setattr(tasks, "_notify_feishu_safe", fake_notify)
    monkeypatch.setattr(tasks, "_notify_feishu_card_safe", fake_notify)

    await tasks.deliver_report_mail(1, [1, 2, 3])

    assert reads == ["a" * 32]  # 3 封邮件只读一次附件
    assert len(batch) == 3
    assert all(mail.extra_attachments is shared for mail in batch)  # 复用同一份 bytes
