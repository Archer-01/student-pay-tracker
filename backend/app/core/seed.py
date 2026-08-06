"""Deterministic dummy data for local development — never used in production.

Populates a realistic spread so every feature has something to show: on-time payers, a chronic
late payer (accumulating drift), an unpaid-cycle gap, an anchor override, an inactive student,
and one student with no phone (exercises the name-only ledger PDF header). The data is fixed
(no randomness) so a fresh seed is reproducible and testable. All dates are in the past.

Exposed via ``tracker db seed`` (see ``app/cli.py``).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.services.override_service import OverrideService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService


@dataclass(frozen=True)
class _Payment:
    for_month: tuple[int, int]  # (year, month) the payment settles
    paid_date: date
    amount: Decimal


@dataclass(frozen=True)
class _Override:
    new_due_date: date
    reason: str


@dataclass(frozen=True)
class _SeedStudent:
    name: str
    phone: str | None
    join_date: date
    fee: Decimal
    status: StudentStatus
    payments: tuple[_Payment, ...]
    overrides: tuple[_Override, ...] = ()


@dataclass(frozen=True)
class SeedSummary:
    students: int
    payments: int
    overrides: int


SEED_STUDENTS: tuple[_SeedStudent, ...] = (
    # Chronic late payer: March cycle left unpaid, then two late settlements -> visible drift.
    _SeedStudent(
        name="Amina Benali",
        phone="+212600112233",
        join_date=date(2023, 3, 5),
        fee=Decimal("300"),
        status=StudentStatus.ACTIVE,
        payments=(
            _Payment((2023, 4), date(2023, 4, 15), Decimal("300")),  # 10 days late
            _Payment((2023, 5), date(2023, 5, 20), Decimal("300")),  # 15 days late
            _Payment((2023, 6), date(2023, 6, 5), Decimal("300")),  # on time
        ),
    ),
    # Reliable payer: on time / slightly early -> zero (or near-zero) drift.
    _SeedStudent(
        name="Youssef El Amrani",
        phone="+212611223344",
        join_date=date(2023, 9, 10),
        fee=Decimal("250"),
        status=StudentStatus.ACTIVE,
        payments=(
            _Payment((2023, 9), date(2023, 9, 10), Decimal("250")),  # on time
            _Payment((2023, 10), date(2023, 10, 9), Decimal("250")),  # a day early
            _Payment((2023, 11), date(2023, 11, 11), Decimal("250")),  # 1 day late
        ),
    ),
    # Has an anchor override (agreed to shift the due date); pays her early cycles a bit late.
    _SeedStudent(
        name="Sara Idrissi",
        phone="+212622334455",
        join_date=date(2024, 1, 15),
        fee=Decimal("350"),
        status=StudentStatus.ACTIVE,
        overrides=(_Override(date(2024, 4, 25), "Agreed to shift the due date to end of month"),),
        payments=(
            _Payment((2024, 1), date(2024, 1, 20), Decimal("350")),  # 5 days late
            _Payment((2024, 2), date(2024, 2, 18), Decimal("350")),  # 3 days late
        ),
    ),
    # No phone on file (ledger PDF shows name only); has an unpaid July gap between payments.
    _SeedStudent(
        name="Omar Tazi",
        phone=None,
        join_date=date(2023, 6, 20),
        fee=Decimal("200"),
        status=StudentStatus.ACTIVE,
        payments=(
            _Payment((2023, 6), date(2023, 6, 25), Decimal("200")),  # 5 days late
            _Payment((2023, 8), date(2023, 8, 28), Decimal("200")),  # July unpaid; Aug 8 days late
        ),
    ),
    # Inactive student (left) — excluded from active-only views and monthly reports.
    _SeedStudent(
        name="Fatima Zahra",
        phone="+212633445566",
        join_date=date(2023, 11, 1),
        fee=Decimal("400"),
        status=StudentStatus.INACTIVE,
        payments=(
            _Payment((2023, 11), date(2023, 11, 1), Decimal("400")),  # on time
            _Payment((2023, 12), date(2023, 12, 10), Decimal("400")),  # 9 days late
        ),
    ),
    # Recent enrollment, paying promptly.
    _SeedStudent(
        name="Mehdi Alaoui",
        phone="+212644556677",
        join_date=date(2024, 3, 5),
        fee=Decimal("300"),
        status=StudentStatus.ACTIVE,
        payments=(
            _Payment((2024, 3), date(2024, 3, 5), Decimal("300")),  # on time
            _Payment((2024, 4), date(2024, 4, 4), Decimal("300")),  # a day early
        ),
    ),
)


def seed_dummy_data(session: Session) -> SeedSummary:
    """Insert :data:`SEED_STUDENTS` (and their overrides/payments) via the service layer.

    Uses the same services the CLI and API use, so the seeded data obeys every domain rule
    (drift math, override ordering, duplicate-payment rejection). Appends — it does not clear
    existing rows; the caller (``tracker db seed``) guards against double-seeding.
    """
    students = StudentService(session)
    payments = PaymentService(session)
    overrides = OverrideService(session)
    n_payments = n_overrides = 0

    for spec in SEED_STUDENTS:
        student = students.enroll(
            name=spec.name,
            phone=spec.phone,
            join_date=spec.join_date,
            fee=spec.fee,
            status=spec.status,
        )
        # Overrides first so any payment for a re-anchored month settles against the new date.
        for ov in spec.overrides:
            overrides.create_override(
                student_id=student.id, new_due_date=ov.new_due_date, reason=ov.reason
            )
            n_overrides += 1
        for pay in spec.payments:
            year, month = pay.for_month
            cycle = payments.cycle_for_month(student.id, year, month)
            payments.record_payment(
                student_id=student.id,
                cycle_number=cycle,
                paid_date=pay.paid_date,
                amount=pay.amount,
            )
            n_payments += 1

    return SeedSummary(students=len(SEED_STUDENTS), payments=n_payments, overrides=n_overrides)
