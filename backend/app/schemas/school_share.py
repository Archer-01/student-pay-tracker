"""Schemas for handing the school its share."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import Money


class ShareMonthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    collected: Decimal
    due: Decimal
    handed_amount: Decimal | None
    handed_on: date | None
    status: str
    remaining: Decimal


class SchoolShareOut(BaseModel):
    percent: Decimal
    # Newest first, from the month of the first payment to this one.
    months: list[ShareMonthOut]
    # What is still to hand over, all months together, and in how many months.
    outstanding: Decimal
    outstanding_months: int


class HandoverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handed_on: date


class HandOverAllIn(HandoverIn):
    # The total the teacher was shown and confirmed: a different one now is a 409, not a guess.
    expected: Money = Field(ge=0)
