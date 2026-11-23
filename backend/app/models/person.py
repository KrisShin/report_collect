"""跨报告去重的人员信息。"""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 五字段规范化后的 SHA-256；唯一索引保证同一人只有一条
    match_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    organization: Mapped[str] = mapped_column(String(512))
    position: Mapped[str] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(32))
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(254))

    has_sent: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    first_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
