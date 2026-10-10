"""报告 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.report_window import to_api_utc


class ReportCreate(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    sort_order: int = 0
    start_at: datetime | None = None
    end_at: datetime | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):  # noqa: ANN001, ANN206
        return value.strip() if isinstance(value, str) else value

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value):  # noqa: ANN001, ANN206
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_window(cls, value: datetime | None) -> datetime | None:
        return to_api_utc(value)

    @model_validator(mode="after")
    def check_window(self):
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            raise ValueError("开始时间必须早于结束时间")
        return self


class ReportUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    sort_order: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):  # noqa: ANN001, ANN206
        return value.strip() if isinstance(value, str) else value

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_window(cls, value: datetime | None) -> datetime | None:
        return to_api_utc(value)


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None = None
    is_active: bool
    sort_order: int
    start_at: datetime | None = None
    end_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_window(cls, value: datetime | None) -> datetime | None:
        return to_api_utc(value)


class ReportAdminRead(ReportRead):
    submission_count: int = 0


class ReportPublic(BaseModel):
    """客户端可见的报告信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    state: str = "open"

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_window(cls, value: datetime | None) -> datetime | None:
        return to_api_utc(value)
