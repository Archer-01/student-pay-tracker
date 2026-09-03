"""Response schemas for the ledger endpoint."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cycle_number: int
    expected_due_date: date
    paid_date: date | None
    days_late: int | None
    amount: Decimal | None
    cumulative_drift: int
    # True when the student was away that month: shown, but neither owed nor accruing drift.
    suspended: bool


class LedgerOut(BaseModel):
    student_id: int
    as_of: date
    cumulative_drift: int
    entries: list[LedgerEntryOut]
