"""Response schemas for the dashboard endpoint."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class StudentDigestOut(BaseModel):
    """One student as the dashboard needs them: who, where, and how far behind."""

    model_config = ConfigDict(from_attributes=True)

    student_id: int
    name: str
    class_label: str | None
    monthly_price: Decimal
    cumulative_drift: int
    months_overdue: int
    amount_owed: Decimal


class DashboardSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: date
    total_collected_this_month: Decimal
    total_outstanding: Decimal
    active_students: int
    leavers_with_debt: int
    owed_by_leavers: Decimal
    # Ranked by money owed, then drift.
    top_debtors: list[StudentDigestOut]
    # Both empty in a healthy database; each is a problem that raises no error on its own.
    unbilled_students: list[StudentDigestOut]
    missing_leave_date: list[StudentDigestOut]
