"""邮件发送记录。"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class MailLog(Base):
    __tablename__ = "mail_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_ids: Mapped[str] = mapped_column(Text, default="[]")
    recipient: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(String(255))
    attachment_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

