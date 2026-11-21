"""Response schemas for the dashboard endpoint."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.reports import ShareOut
from app.services.pricing_service import PriceStatus


class StudentDigestOut(BaseModel):
    """One student as the dashboard needs them: who, where, and how far behind."""

    model_config = ConfigDict(from_attributes=True)

    student_id: int
    name: str
    class_label: str | None
    monthly_price: Decimal
    price_status: PriceStatus
    cumulative_drift: int
    months_overdue: int
    amount_owed: Decimal


class MonthProgressOut(BaseModel):
    """This month's fees, at today's prices, and what has been paid toward them."""

    model_config = ConfigDict(from_attributes=True)

    expected: Decimal
    settled: Decimal
    students_expected: int
    students_settled: int


class DueSoonOut(BaseModel):
    """An unpaid payment falling due in the coming week."""

    model_config = ConfigDict(from_attributes=True)

    student_id: int
    name: str
    class_label: str | None
    due_date: date
    amount: Decimal


class RecordedTodayOut(BaseModel):
    """A payment typed in today, to check for typos; ``for_month`` is "YYYY-MM"."""

    model_config = ConfigDict(from_attributes=True)

    student_id: int
    name: str
    class_label: str | None
    cycle_number: int
    for_month: str
    paid_date: date
    amount: Decimal


class SharePendingOut(BaseModel):
    """Last month's share for the school, still (partly) to hand over."""

    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    remaining: Decimal


class DashboardSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: date
    total_collected_this_month: Decimal
    share_this_month: ShareOut
    total_outstanding: Decimal
    active_students: int
    leavers_with_debt: int
    owed_by_leavers: Decimal
    # Ranked by money owed, then drift.
    top_debtors: list[StudentDigestOut]
    # Both empty in a healthy database; each is a problem that raises no error on its own.
    unbilled_students: list[StudentDigestOut]
    missing_leave_date: list[StudentDigestOut]
    this_month: MonthProgressOut
    # Soonest first: today and the six days after it.
    due_this_week: list[DueSoonOut]
    school_share_pending: SharePendingOut | None
    # Payments recorded today (by when they were typed in, not paid), newest first.
    recorded_today: list[RecordedTodayOut]
