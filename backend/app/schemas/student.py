"""Response schemas for student endpoints (Pydantic v2, separate from the ORM)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import StudentStatus
from app.schemas.money import Money
from app.schemas.pack import PackBriefOut
from app.schemas.school_class import ClassBriefOut


class StudentCreate(BaseModel):
    first_name: str = Field(min_length=1)
    # Optional: some students have no surname on record (a compound given name, say).
    last_name: str | None = None
    phone: str | None = None
    is_repeating: bool = False
    join_date: date
    status: StudentStatus = StudentStatus.ACTIVE
    class_id: int | None = None
    # The pack they're on. Optional: a student can be enrolled before being priced, and simply
    # isn't billed until they have one.
    pack_id: int | None = None
    # Set only when this student doesn't pay the pack price; `price_note` records why.
    custom_price: Money | None = Field(default=None, ge=0)
    price_note: str | None = None

    @field_validator("first_name")
    @classmethod
    def _first_name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("first_name must not be blank")
        return value


class StudentUpdate(BaseModel):
    # extra="forbid" rejects join_date (and typos) with 422 — the anchor is immutable via the API.
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, min_length=1)
    last_name: str | None = None
    phone: str | None = None
    is_repeating: bool | None = None
    status: StudentStatus | None = None
    # Explicit null clears the field; omitting the key leaves it unchanged (see the router).
    class_id: int | None = None
    pack_id: int | None = None
    custom_price: Money | None = Field(default=None, ge=0)
    price_note: str | None = None


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str | None
    # Assembled by the model so every surface renders a name identically.
    full_name: str
    phone: str | None
    is_repeating: bool
    join_date: date
    status: StudentStatus
    class_id: int | None
    school_class: ClassBriefOut | None
    pack_id: int | None
    pack: PackBriefOut | None
    custom_price: Decimal | None
    price_note: str | None
    created_at: datetime


class StudentListItemOut(StudentOut):
    cumulative_drift: int
    months_overdue: int
    # What they owe, in money.
    amount_owed: Decimal
    # The effective price: `custom_price` if set, else the pack's, else zero.
    monthly_price: Decimal


class StudentDetailOut(StudentOut):
    cumulative_drift: int
    months_overdue: int
    amount_owed: Decimal
    monthly_price: Decimal
    next_expected_date: date
    payments_count: int
    total_paid: Decimal
    first_payment_date: date | None
    as_of: date


class DriftOut(BaseModel):
    student_id: int
    as_of: date
    cumulative_drift: int
