"""提交表单 Schema 与字段校验规则。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PHONE_PATTERN = r"^1[3-9]\d{9}$"

SubmissionStatus = Literal["pending", "approved", "rejected", "sent", "failed"]


class SubmissionCreate(BaseModel):
    organization: str = Field(min_length=1, max_length=512)
    position: str = Field(min_length=1, max_length=512)
    name: str = Field(min_length=1, max_length=32)
    phone: str = Field(min_length=1, max_length=20)
    email: EmailStr

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
    organization: str
    position: str
    name: str
    phone: str
    phone_source: str
    email: EmailStr
    status: SubmissionStatus
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
