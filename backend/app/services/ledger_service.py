"""The ledger — a student's full cycle-by-cycle view including unpaid gaps.

Paid cycles display their *frozen* values (the recorded due date/lateness — the audit truth);
unpaid cycles show ``None`` for paid_date/days_late/amount and their live override-aware due
date, contributing 0 to drift. The running ``cumulative_drift`` on the last entry equals
:meth:`LedgerService.cumulative_drift` for the same ``as_of``.

**Suspension.** An unpaid cycle whose due date falls outside every enrollment period is marked
``suspended``: the student wasn't attending that month, so it is shown as "away" rather than
counted as debt. Suspension only ever removes *future* accrual — it can't subtract drift that has
already happened, because drift comes from recorded payments, which are never suspended.
``schedule.py`` is untouched by any of this: the schedule is still generated from the immutable
anchor, and absence is a filter applied on top.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Student
from app.repos import EnrollmentRepo, OverrideRepo, PaymentRepo, StudentRepo
from app.services.exceptions import StudentNotFoundError
from app.services.pricing_service import PricingService
from app.services.schedule import generate_expected_due_dates, next_expected_date


@dataclass(frozen=True)
class LedgerEntry:
    cycle_number: int
    expected_due_date: date
    paid_date: date | None
    days_late: int | None
    amount: Decimal | None
    cumulative_drift: int
    # True when this month fell outside every enrollment period: the student was away, so it is
    # neither owed nor able to accrue drift. Always False for a cycle that was actually paid.
    suspended: bool = False


@dataclass(frozen=True)
class StudentSummary:
    cumulative_drift: int
    months_overdue: int
    amount_owed: Decimal
    next_expected_date: date
    payments_count: int
    total_paid: Decimal
    # Derived, never stored: one less thing to keep in sync when a payment is corrected. Not the
    # same as join_date — the gap between them is itself informative.
    first_payment_date: date | None


class LedgerService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.payments = PaymentRepo(session)
        self.overrides = OverrideRepo(session)
        self.enrollment = EnrollmentRepo(session)
        self.pricing = PricingService(session)

    def _require_student_join(self, student_id: int) -> date:
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)
        return student.join_date

    def _attending_on(self, student_id: int) -> Callable[[date], bool]:
        """Predicate: was the student enrolled on this date?

        Built once per ledger pass rather than queried per cycle. With no periods recorded at all
        (a database that predates them) everything counts as attended, so behaviour is unchanged.
        """
        periods = self.enrollment.list_for_student(student_id)
        if not periods:
            return lambda _due: True

        def attending(due: date) -> bool:
            return any(
                period.entry_date <= due
                and (period.leave_date is None or due <= period.leave_date)
                for period in periods
            )

        return attending

    def get_ledger(self, student_id: int, as_of: date) -> list[LedgerEntry]:
        join_date = self._require_student_join(student_id)
        override_dates = [o.new_due_date for o in self.overrides.list_for_student(student_id)]
        live_dues = generate_expected_due_dates(join_date, as_of, override_dates)

        payments_by_cycle = {p.cycle_number: p for p in self.payments.list_for_student(student_id)}
        unpaid = {c for c in range(len(live_dues)) if c not in payments_by_cycle}
        # A paid cycle counts once its *recorded* (frozen) due date has arrived.
        paid = {c for c, p in payments_by_cycle.items() if p.expected_due_date <= as_of}

        attending = self._attending_on(student_id)
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
                due = live_dues[cycle]
                entries.append(
                    LedgerEntry(
                        cycle_number=cycle,
                        expected_due_date=due,
                        paid_date=None,
                        days_late=None,
                        amount=None,
                        cumulative_drift=running,
                        # A paid cycle is never suspended (handled above): a recorded payment is
                        # audit truth regardless of what the attendance history says.
                        suspended=not attending(due),
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

    def unpaid_due_dates(self, student: Student, entries: list[LedgerEntry]) -> list[date]:
        """Due dates of unpaid cycles that actually cost something.

        Arrears are the unpaid cycles due by ``as_of``, minus any the student was away for and
        any priced at zero — a student with no pack, or on a free one, is not in debt.
        """
        return [
            e.expected_due_date
            for e in entries
            if e.paid_date is None and not e.suspended and self.pricing.billable(student)
        ]

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
        unpaid_due = self.unpaid_due_dates(student, entries)
        return StudentSummary(
            cumulative_drift=entries[-1].cumulative_drift if entries else 0,
            months_overdue=len(unpaid_due),
            amount_owed=self.pricing.amount_for_cycles(student, unpaid_due),
            next_expected_date=self.next_expected_date(student_id, as_of),
            payments_count=len(payments),
            total_paid=sum((p.amount for p in payments), Decimal("0")),
            first_payment_date=min((p.paid_date for p in payments), default=None),
        )
