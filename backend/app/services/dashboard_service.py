"""Dashboard aggregates for the teacher's overview.

- collected this month: sum of payment amounts by *paid date* within ``as_of``'s calendar month.
- outstanding: money owed across all overdue months by *active* students
  (unpaid cycles due <= as_of, priced by PricingService).
- top latecomers: active students with the most cumulative drift (drift > 0).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.repos import PaymentRepo, StudentRepo
from app.services.debt_service import DebtService
from app.services.ledger_service import LedgerService
from app.services.pricing_service import PricingService
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
    # Money owed by students who have already left — separate from `total_outstanding`, which
    # covers the ones still attending. Chasing the two groups is a different conversation.
    leavers_with_debt: int
    owed_by_leavers: Decimal


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.payments = PaymentRepo(session)
        self.ledger = LedgerService(session)
        self.pricing = PricingService(session)
        self.debts = DebtService(session)

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
            unpaid_due = self.ledger.unpaid_due_dates(student, entries)
            outstanding += self.pricing.amount_for_cycles(student, unpaid_due)
            drift = entries[-1].cumulative_drift if entries else 0
            if drift > 0:
                latecomers.append(Latecomer(student.id, student.full_name, drift))

        latecomers.sort(key=lambda latecomer: latecomer.cumulative_drift, reverse=True)
        leavers = self.debts.leavers_with_debt()
        return DashboardSummary(
            as_of=as_of,
            leavers_with_debt=len(leavers),
            owed_by_leavers=sum((s.amount_owed for s in leavers), Decimal("0")),
            total_collected_this_month=collected,
            total_outstanding=outstanding,
            top_latecomers=latecomers[:top_n],
        )
