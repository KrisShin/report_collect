"""用户提交的报告信息。"""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("report_id", "phone", name="uq_submissions_report_phone"),
        UniqueConstraint("report_id", "email", name="uq_submissions_report_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("reports.id"), index=True, nullable=True
    )

    organization: Mapped[str] = mapped_column(String(512))
    position: Mapped[str] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(32), index=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    phone_source: Mapped[str] = mapped_column(String(16), default="manual")
    email: Mapped[str] = mapped_column(String(254), index=True)
    wx_openid: Mapped[str | None] = mapped_column(String(64), index=True)
    wx_unionid: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)

    # 是否已处理（发送邮件等后续动作）
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_action: Mapped[str | None] = mapped_column(String(32))

    # DeepSeek V4 Flash 内容质量判定
    ai_flag: Mapped[str | None] = mapped_column(String(16), index=True)
    ai_score: Mapped[float | None] = mapped_column(Float)
    ai_reason: Mapped[str | None] = mapped_column(String(512))

    review_note: Mapped[str | None] = mapped_column(String(512))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("admin_users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    mail_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mail_error: Mapped[str | None] = mapped_column(Text)

    feishu_status: Mapped[str | None] = mapped_column(String(16))
    feishu_error: Mapped[str | None] = mapped_column(Text)

    client_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
