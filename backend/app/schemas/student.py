"""Response schemas for student endpoints (Pydantic v2, separate from the ORM)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import StudentStatus


class StudentCreate(BaseModel):
    name: str = Field(min_length=1)
    phone: str | None = None
    join_date: date
    fee: Decimal = Field(ge=0)  # free/scholarship students are allowed
    status: StudentStatus = StudentStatus.ACTIVE

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value


class StudentUpdate(BaseModel):
    # extra="forbid" rejects join_date (and typos) with 422 — the anchor is immutable via the API.
    model_config = ConfigDict(extra="forbid")

    phone: str | None = None
    fee: Decimal | None = Field(default=None, ge=0)
    status: StudentStatus | None = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
    join_date: date
    fee: Decimal
    status: StudentStatus
    created_at: datetime


class StudentListItemOut(StudentOut):
    cumulative_drift: int
    months_overdue: int


class StudentDetailOut(StudentOut):
    cumulative_drift: int
    months_overdue: int
    next_expected_date: date
    payments_count: int
    total_paid: Decimal
    as_of: date


class DriftOut(BaseModel):
    student_id: int
    as_of: date
    cumulative_drift: int
