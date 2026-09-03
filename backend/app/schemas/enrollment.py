"""Request/response schemas for enrollment periods (leave and return)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    entry_date: date
    # NULL means the student is currently attending.
    leave_date: date | None
    leave_reason: str | None
    created_at: datetime


class ReturnResultOut(PeriodOut):
    """A reopened period, plus what the returning student still owes.

    The return itself is never refused — re-admitting a debtor is the teacher's call. This is the
    moment they most need to know, so the figure travels back with the response.
    """

    amount_owed: Decimal
    months_owed: int
    debt_warning: str | None = None


class LeaveRequest(BaseModel):
    leave_date: date
    reason: str | None = None


class ReturnRequest(BaseModel):
    entry_date: date


class PeriodAmend(BaseModel):
    # extra="forbid" rejects typos with 422 rather than silently ignoring them.
    model_config = ConfigDict(extra="forbid")

    entry_date: date | None = None
    leave_date: date | None = None
    reason: str | None = None
