"""Request/response schemas for payments."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PaymentCreate(BaseModel):
    paid_date: date
    amount: Decimal = Field(gt=0)  # a recorded payment is real money
    cycle_number: int | None = Field(default=None, ge=0)
    for_month: str | None = Field(default=None, description="Which month it settles, YYYY-MM")

    @field_validator("paid_date")
    @classmethod
    def _not_in_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("paid_date must not be in the future")
        return value

    @field_validator("for_month")
    @classmethod
    def _valid_month(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = value.split("-")
        try:
            if len(parts) != 2:
                raise ValueError
            date(int(parts[0]), int(parts[1]), 1)
        except ValueError as exc:
            raise ValueError("for_month must be YYYY-MM") from exc
        return value

    @model_validator(mode="after")
    def _exactly_one_selector(self) -> "PaymentCreate":
        if (self.cycle_number is None) == (self.for_month is None):
            raise ValueError("provide exactly one of cycle_number or for_month")
        return self


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    cycle_number: int
    paid_date: date
    expected_due_date: date
    days_late: int
    amount: Decimal
    created_at: datetime
