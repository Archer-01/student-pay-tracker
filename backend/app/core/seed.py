"""Deterministic dummy data for local development — never used in production.

Populates a realistic spread so every feature has something to show: on-time payers, a chronic
late payer (accumulating drift), an unpaid-cycle gap, an anchor override, an inactive student,
one student with no phone, one repeating the year, and one whose name is a compound given name
with no surname ("Fatima Zahra" — the case a naive first/last split gets wrong). Classes cover
several
levels, including an empty one (so "delete an empty class" is reachable) and one unassigned
student (so the "Unassigned" filter has something to show). The full 4 x 6 pack grid is created,
with prices rising by level, plus the pricing cases worth seeing: a student on an agreed price
below their pack's, and one with no pack at all (so the "not billed yet" state is visible). The
data is fixed (no randomness) so a fresh seed is reproducible and testable. All dates are in the
past.

Exposed via ``tracker db seed`` (see ``app/cli.py``).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import ClassLevel, StudentStatus
from app.services.class_service import ClassService
from app.services.enrollment_service import EnrollmentService
from app.services.override_service import OverrideService
from app.services.pack_service import PackService
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
    first_name: str
    last_name: str | None
    phone: str | None
    join_date: date
    status: StudentStatus
    payments: tuple[_Payment, ...]
    overrides: tuple[_Override, ...] = ()
    # (level, name) of the class they belong to; None leaves them unassigned.
    school_class: tuple[ClassLevel, str] | None = None
    # (offering, level) of the pack they're on; None means not billed yet.
    pack: tuple[str, ClassLevel] | None = None
    # Set only when they don't pay the pack price.
    custom_price: Decimal | None = None
    price_note: str | None = None
    is_repeating: bool = False
    # (leave date, reason) — recorded after the payments, so the ledger shows suspended months.
    left_on: tuple[date, str] | None = None
    returned_on: date | None = None


@dataclass(frozen=True)
class SeedSummary:
    students: int
    payments: int
    overrides: int
    classes: int
    packs: int


# Includes an empty class (3AC) so the "delete an empty class" path is reachable from seeded data.
SEED_CLASSES: tuple[tuple[ClassLevel, str], ...] = (
    (ClassLevel.AC1, "Groupe A"),
    (ClassLevel.AC3, "Groupe A"),
    (ClassLevel.TC, "Groupe A"),
    (ClassLevel.BAC1, "Groupe A"),
    (ClassLevel.BAC2, "Groupe A"),
    (ClassLevel.BAC2, "Groupe B"),
)


# The four offerings the teacher sells, priced across all six levels: 4 x 6 = 24 packs. Prices
# rise with level, which is exactly why `level` lives on the pack rather than on a shared offering.
SEED_OFFERINGS: tuple[tuple[str, tuple[str, ...], dict[ClassLevel, Decimal]], ...] = (
    (
        "Maths seul",
        ("Maths",),
        {
            ClassLevel.AC1: Decimal("100"),
            ClassLevel.AC2: Decimal("100"),
            ClassLevel.AC3: Decimal("120"),
            ClassLevel.TC: Decimal("120"),
            ClassLevel.BAC1: Decimal("140"),
            ClassLevel.BAC2: Decimal("150"),
        },
    ),
    (
        "Physique seul",
        ("Physique",),
        {
            ClassLevel.AC1: Decimal("100"),
            ClassLevel.AC2: Decimal("100"),
            ClassLevel.AC3: Decimal("120"),
            ClassLevel.TC: Decimal("120"),
            ClassLevel.BAC1: Decimal("140"),
            ClassLevel.BAC2: Decimal("150"),
        },
    ),
    (
        "Maths + Physique",
        ("Maths", "Physique"),
        {
            ClassLevel.AC1: Decimal("170"),
            ClassLevel.AC2: Decimal("170"),
            ClassLevel.AC3: Decimal("190"),
            ClassLevel.TC: Decimal("190"),
            ClassLevel.BAC1: Decimal("220"),
            ClassLevel.BAC2: Decimal("240"),
        },
    ),
    (
        "Pack complet",
        ("Maths", "Physique", "Français", "Anglais"),
        {
            ClassLevel.AC1: Decimal("220"),
            ClassLevel.AC2: Decimal("220"),
            ClassLevel.AC3: Decimal("250"),
            ClassLevel.TC: Decimal("250"),
            ClassLevel.BAC1: Decimal("280"),
            ClassLevel.BAC2: Decimal("300"),
        },
    ),
)


SEED_STUDENTS: tuple[_SeedStudent, ...] = (
    # Chronic late payer: March cycle left unpaid, then two late settlements -> visible drift.
    _SeedStudent(
        first_name="Amina",
        last_name="Benali",
        school_class=(ClassLevel.BAC2, "Groupe A"),
        pack=("Maths + Physique", ClassLevel.BAC2),
        phone="+212600112233",
        join_date=date(2023, 3, 5),
        status=StudentStatus.ACTIVE,
        payments=(
            _Payment((2023, 4), date(2023, 4, 15), Decimal("300")),  # 10 days late
            _Payment((2023, 5), date(2023, 5, 20), Decimal("300")),  # 15 days late
            _Payment((2023, 6), date(2023, 6, 5), Decimal("300")),  # on time
        ),
    ),
    # Reliable payer: on time / slightly early -> zero (or near-zero) drift.
    _SeedStudent(
        first_name="Youssef",
        last_name="El Amrani",
        school_class=(ClassLevel.BAC2, "Groupe A"),
        pack=("Pack complet", ClassLevel.BAC2),
        phone="+212611223344",
        join_date=date(2023, 9, 10),
        status=StudentStatus.ACTIVE,
        payments=(
            _Payment((2023, 9), date(2023, 9, 10), Decimal("250")),  # on time
            _Payment((2023, 10), date(2023, 10, 9), Decimal("250")),  # a day early
            _Payment((2023, 11), date(2023, 11, 11), Decimal("250")),  # 1 day late
        ),
    ),
    # Has an anchor override (agreed to shift the due date); pays her early cycles a bit late.
    _SeedStudent(
        first_name="Sara",
        last_name="Idrissi",
        is_repeating=True,
        school_class=(ClassLevel.BAC1, "Groupe A"),
        # An agreed price below the pack's 280, with the reason recorded beside it.
        pack=("Pack complet", ClassLevel.BAC1),
        custom_price=Decimal("200"),
        price_note="remise fratrie",
        phone="+212622334455",
        join_date=date(2024, 1, 15),
        status=StudentStatus.ACTIVE,
        overrides=(_Override(date(2024, 4, 25), "Agreed to shift the due date to end of month"),),
        payments=(
            _Payment((2024, 1), date(2024, 1, 20), Decimal("350")),  # 5 days late
            _Payment((2024, 2), date(2024, 2, 18), Decimal("350")),  # 3 days late
        ),
    ),
    # No phone on file (ledger PDF shows name only); has an unpaid July gap between payments.
    _SeedStudent(
        first_name="Omar",
        last_name="Tazi",
        # Left and came back — the case that must not reset his drift.
        left_on=(date(2023, 9, 30), "Pause"),
        returned_on=date(2024, 1, 15),
        school_class=(ClassLevel.TC, "Groupe A"),
        pack=("Maths seul", ClassLevel.TC),
        phone=None,
        join_date=date(2023, 6, 20),
        status=StudentStatus.ACTIVE,
        payments=(
            _Payment((2023, 6), date(2023, 6, 25), Decimal("200")),  # 5 days late
            _Payment((2023, 8), date(2023, 8, 28), Decimal("200")),  # July unpaid; Aug 8 days late
        ),
    ),
    # Left mid-year — excluded from active-only views, and not billed for months away.
    _SeedStudent(
        first_name="Fatima Zahra",
        last_name=None,
        # Left mid-year: the months after are shown as "away" and are not owed.
        left_on=(date(2024, 1, 31), "Déménagement"),
        school_class=(ClassLevel.AC1, "Groupe A"),
        pack=("Maths + Physique", ClassLevel.AC1),
        phone="+212633445566",
        join_date=date(2023, 11, 1),
        status=StudentStatus.ACTIVE,
        payments=(
            _Payment((2023, 11), date(2023, 11, 1), Decimal("400")),  # on time
            _Payment((2023, 12), date(2023, 12, 10), Decimal("400")),  # 9 days late
        ),
    ),
    # No class and no pack: exercises the "Unassigned" filter and the not-yet-billed state a
    # student is in before the teacher puts them on a pack.
    _SeedStudent(
        first_name="Mehdi",
        last_name="Alaoui",
        phone="+212644556677",
        join_date=date(2024, 3, 5),
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
    classes = ClassService(session)
    packs = PackService(session)
    enrollment = EnrollmentService(session)
    n_payments = n_overrides = 0

    # get_or_create, not create: seeding appends (see the docstring), so a second run must
    # place its students into the existing classes rather than collide on (level, name).
    class_ids = {
        (level, name): classes.get_or_create(level=level, name=name).id
        for level, name in SEED_CLASSES
    }

    # get_or_create semantics for packs too: seeding appends, so a second run reuses the grid.
    pack_ids: dict[tuple[str, ClassLevel], int] = {}
    for name, subjects, prices in SEED_OFFERINGS:
        for level, price in prices.items():
            existing = packs.packs.find(name, level)
            pack = existing or packs.create(
                name=name, level=level, price=price, subjects=list(subjects)
            )
            pack_ids[(name, level)] = pack.id

    for spec in SEED_STUDENTS:
        student = students.enroll(
            first_name=spec.first_name,
            last_name=spec.last_name,
            is_repeating=spec.is_repeating,
            phone=spec.phone,
            join_date=spec.join_date,
            status=spec.status,
            class_id=None if spec.school_class is None else class_ids[spec.school_class],
            pack_id=None if spec.pack is None else pack_ids[spec.pack],
            custom_price=spec.custom_price,
            price_note=spec.price_note,
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

        # Attendance last: a leave date closes the period the payments were recorded against.
        if spec.left_on is not None:
            leave_date, reason = spec.left_on
            enrollment.leave(student.id, leave_date=leave_date, reason=reason)
            if spec.returned_on is not None:
                enrollment.return_(student.id, entry_date=spec.returned_on)

    return SeedSummary(
        students=len(SEED_STUDENTS),
        payments=n_payments,
        overrides=n_overrides,
        classes=len(SEED_CLASSES),
        packs=len(pack_ids),
    )
