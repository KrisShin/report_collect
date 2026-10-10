"""提交表单 Schema 与字段校验规则。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PHONE_PATTERN = r"^1[3-9]\d{9}$"
# 只允许 ASCII 域名与 TLD，拒绝中文/国际化域名
EMAIL_PATTERN = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$"

SubmissionStatus = Literal["pending", "approved", "rejected", "sent", "failed"]


class SubmissionCreate(BaseModel):
    report_id: str
    organization: str = Field(min_length=1, max_length=512)
    position: str = Field(min_length=1, max_length=512)
    name: str = Field(min_length=1, max_length=32)
    phone: str = Field(min_length=1, max_length=20)
    email: EmailStr

    @field_validator("report_id", mode="before")
    @classmethod
    def normalize_report_id(cls, value):  # noqa: ANN001, ANN206
        return str(value) if value is not None else value

    @field_validator("report_id")
    @classmethod
    def validate_report_id(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"[0-9a-f]{32}", value):
            raise ValueError("报告链接无效，请使用管理员提供的填报链接")
        return value

    @field_validator("email")
    @classmethod
    def validate_ascii_email(cls, value: str) -> str:
        import re

        value = value.lower()
        if not value.isascii() or not re.fullmatch(EMAIL_PATTERN, value):
            raise ValueError("请输入有效的邮箱地址（仅支持英文字符）")
        return value

    @field_validator("organization", "position", "name", "phone", "email", mode="before")
    @classmethod
    def strip_text(cls, value):  # noqa: ANN001, ANN206
        return value.strip() if isinstance(value, str) else value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        import re

        if not re.fullmatch(PHONE_PATTERN, value):
            raise ValueError("请输入有效的 11 位手机号")
        return value


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: str | None = None
    report_title: str | None = None
    organization: str
    position: str
    name: str
    phone: str
    phone_source: str
    email: EmailStr
    status: SubmissionStatus
    is_processed: bool = False
    processed_at: datetime | None = None
    processed_action: str | None = None
    ai_flag: str | None = None
    ai_score: float | None = None
    ai_reason: str | None = None
    review_note: str | None = None
    submitted_at: datetime
    mail_sent_at: datetime | None = None
    feishu_status: str | None = None


class SubmissionCreated(BaseModel):
    id: int
    status: SubmissionStatus
    message: str = "提交成功，等待管理员审核后发送到邮箱"


class ReviewRequest(BaseModel):
    status: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=512)
