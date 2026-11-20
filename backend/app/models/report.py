"""报告（可创建多个，客户端按 uuid hex id 填报）。"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_report_id() -> str:
    """32 位 uuid4 hex，避免被猜测/遍历。"""

    return uuid4().hex


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_report_id)
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # 填报时间段（naive UTC 存库，可空表示不限制）
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 报告级邮件设置；全部可空，为空时回退全局模板/附件/默认主题
    email_subject: Mapped[str | None] = mapped_column(String(255))
    email_template_html: Mapped[str | None] = mapped_column(Text)
    email_template_name: Mapped[str | None] = mapped_column(String(255))
    email_template_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    @property
    def has_email_template(self) -> bool:
        return bool(self.email_template_html)
