"""Response schemas for the leavers-with-debt list and write-offs."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.student import StudentOut


class WriteoffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    amount: Decimal
    reason: str
    created_at: datetime


class DebtStatusOut(BaseModel):
    """What a student owed when they left. ``left_on`` is null while they're still attending."""

    student: StudentOut
    left_on: date | None
    amount_owed: Decimal
    months_owed: int
    left_with_debt: bool
    written_off: WriteoffOut | None


class LeaversOut(BaseModel):
    leavers: list[DebtStatusOut]
    total_owed: Decimal


class WriteoffCreate(BaseModel):
    reason: str = Field(min_length=1)
