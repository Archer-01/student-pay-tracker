"""Schemas for handing the school its share."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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


class HandoverIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    handed_on: date
