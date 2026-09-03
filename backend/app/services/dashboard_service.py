"""Dashboard aggregates — what the teacher needs to act on today.

Three questions, in the order they get asked:

- **What came in?** Payments by *paid date* within ``as_of``'s calendar month.
- **Who owes me?** Students ranked by **money owed**, not by drift. Drift is the product's core
  metric and still travels on every row, but a student with 25 days of drift who is paid up is not
  someone to chase, while one with thirteen unpaid months is.
- **What's quietly wrong?** Problems that produce no error and no bill: a student on no pack is
  charged nothing, month after month, and nothing else in the app says so.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Student, StudentStatus
from app.repos import PaymentRepo, StudentRepo
from app.services.debt_service import DebtService
from app.services.enrollment_service import EnrollmentService
from app.services.ledger_service import LedgerService
from app.services.pricing_service import PricingService
from app.services.schedule import add_months


@dataclass(frozen=True)
class StudentDigest:
    """One student as the dashboard needs them: who, where, and how far behind."""

    student_id: int
    name: str
    class_label: str | None
    monthly_price: Decimal
    cumulative_drift: int
    months_overdue: int
    amount_owed: Decimal


@dataclass(frozen=True)
class DashboardSummary:
    as_of: date
    total_collected_this_month: Decimal
    total_outstanding: Decimal
    active_students: int
    # Ranked by money owed, then by drift — the order you would work down the list in.
    top_debtors: list[StudentDigest]
    # Money owed by students who have already left. Separate from `total_outstanding`, which
    # covers the ones still attending: chasing the two groups is a different conversation.
    leavers_with_debt: int
    owed_by_leavers: Decimal
    # --- Silent problems, each empty in a healthy database -------------------
    # Attending but priced at nothing: no pack and no agreed price, so they are invoiced zero
    # every month and appear in no arrears figure.
    unbilled_students: list[StudentDigest]
    # Marked as having left, yet still holding an open attendance period — the state migration
    # 0006 leaves behind, because it refuses to invent a departure date. Their billing keeps
    # running until a real leave is recorded.
    missing_leave_date: list[StudentDigest]


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.payments = PaymentRepo(session)
        self.ledger = LedgerService(session)
        self.pricing = PricingService(session)
        self.debts = DebtService(session)
        self.enrollment = EnrollmentService(session)

    def get_summary(self, as_of: date, top_n: int = 5) -> DashboardSummary:
        month_start = as_of.replace(day=1)
        next_month_start = add_months(month_start, 1)
        collected = sum(
            (p.amount for p in self.payments.list_paid_between(month_start, next_month_start)),
            Decimal("0"),
        )

        outstanding = Decimal("0")
        debtors: list[StudentDigest] = []
        unbilled: list[StudentDigest] = []
        active = self.students.list(status=StudentStatus.ACTIVE)
        for student in active:
            digest = self._digest(student, as_of)
            outstanding += digest.amount_owed
            if digest.monthly_price == 0:
                unbilled.append(digest)
            elif digest.amount_owed > 0 or digest.cumulative_drift > 0:
                debtors.append(digest)

        # Money first, drift as the tie-break: two students owing the same are ordered by how
        # long they have been making a habit of it.
        debtors.sort(key=lambda d: (d.amount_owed, d.cumulative_drift), reverse=True)

        leavers = self.debts.leavers_with_debt()
        return DashboardSummary(
            as_of=as_of,
            total_collected_this_month=collected,
            total_outstanding=outstanding,
            active_students=len(active),
            top_debtors=debtors[:top_n],
            leavers_with_debt=len(leavers),
            owed_by_leavers=sum((s.amount_owed for s in leavers), Decimal("0")),
            unbilled_students=unbilled,
            missing_leave_date=[
                self._digest(student, as_of)
                for student in self.students.list(status=StudentStatus.INACTIVE)
                if self.enrollment.is_attending(student.id)
            ],
        )

    def _digest(self, student: Student, as_of: date) -> StudentDigest:
        summary = self.ledger.student_summary(student.id, as_of)
        return StudentDigest(
            student_id=student.id,
            name=student.full_name,
            class_label=(
                None
                if student.school_class is None
                else f"{student.school_class.level.value} — {student.school_class.name}"
            ),
            monthly_price=self.pricing.price_of(student),
            cumulative_drift=summary.cumulative_drift,
            months_overdue=summary.months_overdue,
            amount_owed=summary.amount_owed,
        )
