"""Dashboard aggregates for the teacher's overview.

- collected this month: sum of payment amounts by *paid date* within ``as_of``'s calendar month.
- outstanding: money owed across all overdue months by *active* students
  (unpaid cycles due <= as_of, times each student's fee).
- top latecomers: active students with the most cumulative drift (drift > 0).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.repos import PaymentRepo, StudentRepo
from app.services.ledger_service import LedgerService
from app.services.schedule import add_months


@dataclass(frozen=True)
class Latecomer:
    student_id: int
    name: str
    cumulative_drift: int


@dataclass(frozen=True)
class DashboardSummary:
    as_of: date
    total_collected_this_month: Decimal
    total_outstanding: Decimal
    top_latecomers: list[Latecomer]


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.payments = PaymentRepo(session)
        self.ledger = LedgerService(session)

    def get_summary(self, as_of: date, top_n: int = 5) -> DashboardSummary:
        month_start = as_of.replace(day=1)
        next_month_start = add_months(month_start, 1)
        collected = sum(
            (p.amount for p in self.payments.list_paid_between(month_start, next_month_start)),
            Decimal("0"),
        )

        outstanding = Decimal("0")
        latecomers: list[Latecomer] = []
        for student in self.students.list(status=StudentStatus.ACTIVE):
            entries = self.ledger.get_ledger(student.id, as_of)
            unpaid_due = sum(1 for e in entries if e.paid_date is None)
            outstanding += unpaid_due * student.fee
            drift = entries[-1].cumulative_drift if entries else 0
            if drift > 0:
                latecomers.append(Latecomer(student.id, student.name, drift))

        latecomers.sort(key=lambda latecomer: latecomer.cumulative_drift, reverse=True)
        return DashboardSummary(
            as_of=as_of,
            total_collected_this_month=collected,
            total_outstanding=outstanding,
            top_latecomers=latecomers[:top_n],
        )
