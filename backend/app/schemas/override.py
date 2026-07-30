"""Request/response schemas for anchor overrides."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OverrideCreate(BaseModel):
    new_due_date: date
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class OverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    new_due_date: date
    reason: str
    created_at: datetime
