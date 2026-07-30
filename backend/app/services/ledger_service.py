"""The ledger — a student's full cycle-by-cycle view including unpaid gaps.

Paid cycles display their *frozen* values (the recorded due date/lateness — the audit truth);
unpaid cycles show ``None`` for paid_date/days_late/amount and their live override-aware due
date, contributing 0 to drift. The running ``cumulative_drift`` on the last entry equals
:meth:`LedgerService.cumulative_drift` for the same ``as_of``.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repos import OverrideRepo, PaymentRepo, StudentRepo
from app.services.exceptions import StudentNotFoundError
from app.services.schedule import generate_expected_due_dates, next_expected_date


@dataclass(frozen=True)
class LedgerEntry:
    cycle_number: int
    expected_due_date: date
    paid_date: date | None
    days_late: int | None
    amount: Decimal | None
    cumulative_drift: int


@dataclass(frozen=True)
class StudentSummary:
    cumulative_drift: int
    months_overdue: int
    next_expected_date: date
    payments_count: int
    total_paid: Decimal


class LedgerService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.payments = PaymentRepo(session)
        self.overrides = OverrideRepo(session)

    def _require_student_join(self, student_id: int) -> date:
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)
        return student.join_date

    def get_ledger(self, student_id: int, as_of: date) -> list[LedgerEntry]:
        join_date = self._require_student_join(student_id)
        override_dates = [o.new_due_date for o in self.overrides.list_for_student(student_id)]
        live_dues = generate_expected_due_dates(join_date, as_of, override_dates)

        payments_by_cycle = {p.cycle_number: p for p in self.payments.list_for_student(student_id)}
        unpaid = {c for c in range(len(live_dues)) if c not in payments_by_cycle}
        # A paid cycle counts once its *recorded* (frozen) due date has arrived.
        paid = {c for c, p in payments_by_cycle.items() if p.expected_due_date <= as_of}

        entries: list[LedgerEntry] = []
        running = 0
        for cycle in sorted(unpaid | paid):
            payment = payments_by_cycle.get(cycle)
            if payment is not None:
                running += max(0, payment.days_late)
                entries.append(
                    LedgerEntry(
                        cycle_number=cycle,
                        expected_due_date=payment.expected_due_date,
                        paid_date=payment.paid_date,
                        days_late=payment.days_late,
                        amount=payment.amount,
                        cumulative_drift=running,
                    )
                )
            else:
                entries.append(
                    LedgerEntry(
                        cycle_number=cycle,
                        expected_due_date=live_dues[cycle],
                        paid_date=None,
                        days_late=None,
                        amount=None,
                        cumulative_drift=running,
                    )
                )
        return entries

    def cumulative_drift(self, student_id: int, as_of: date) -> int:
        """Sum of frozen ``max(0, days_late)`` over cycles whose recorded due date is <= as_of."""
        self._require_student_join(student_id)  # validate existence
        return sum(
            max(0, p.days_late)
            for p in self.payments.list_for_student(student_id)
            if p.expected_due_date <= as_of
        )

    def next_expected_date(self, student_id: int, as_of: date) -> date:
        """The next scheduled due date on or after ``as_of`` (override-aware)."""
        join_date = self._require_student_join(student_id)
        override_dates = [o.new_due_date for o in self.overrides.list_for_student(student_id)]
        return next_expected_date(join_date, as_of, override_dates)

    def student_summary(self, student_id: int, as_of: date) -> StudentSummary:
        """Compact per-student summary for the detail endpoint."""
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)
        payments = self.payments.list_for_student(student_id)
        entries = self.get_ledger(student_id, as_of)
        # Arrears = unpaid cycles due by as_of; free students (fee 0) owe nothing.
        months_overdue = 0 if student.fee == 0 else sum(1 for e in entries if e.paid_date is None)
        return StudentSummary(
            cumulative_drift=entries[-1].cumulative_drift if entries else 0,
            months_overdue=months_overdue,
            next_expected_date=self.next_expected_date(student_id, as_of),
            payments_count=len(payments),
            total_paid=sum((p.amount for p in payments), Decimal("0")),
        )
