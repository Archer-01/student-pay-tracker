"""Repository tests — thin CRUD over the models, no business logic.

Repos operate on a caller-supplied ``Session`` and flush (to assign PKs) but never commit;
the service layer / test owns the transaction.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import AnchorOverride, Payment, Student, StudentStatus
from app.repos import OverrideRepo, PaymentRepo, StudentRepo


def _make_student(name: str = "Amina", status: StudentStatus = StudentStatus.ACTIVE) -> Student:
    return Student(
        name=name,
        phone="+212600000000",
        join_date=date(2023, 3, 5),
        fee=Decimal("300.00"),
        status=status,
    )


def _make_payment(student_id: int, cycle_number: int) -> Payment:
    return Payment(
        student_id=student_id,
        cycle_number=cycle_number,
        paid_date=date(2023, 4, 10),
        expected_due_date=date(2023, 4, 5),
        days_late=5,
        amount=Decimal("300.00"),
    )


# --------------------------------------------------------------------------- #
# StudentRepo
# --------------------------------------------------------------------------- #


def test_student_create_and_get(db_session: Session) -> None:
    repo = StudentRepo(db_session)
    created = repo.create(_make_student())
    assert created.id is not None
    assert repo.get(created.id) is created


def test_student_get_missing_returns_none(db_session: Session) -> None:
    assert StudentRepo(db_session).get(999) is None


def test_student_list_and_status_filter(db_session: Session) -> None:
    repo = StudentRepo(db_session)
    repo.create(_make_student(name="Active One", status=StudentStatus.ACTIVE))
    repo.create(_make_student(name="Left One", status=StudentStatus.INACTIVE))

    assert len(repo.list()) == 2
    active = repo.list(status=StudentStatus.ACTIVE)
    assert [s.name for s in active] == ["Active One"]


def test_student_delete_without_history(db_session: Session) -> None:
    repo = StudentRepo(db_session)
    student = repo.create(_make_student())
    repo.delete(student)
    assert repo.get(student.id) is None


# --------------------------------------------------------------------------- #
# PaymentRepo
# --------------------------------------------------------------------------- #


def test_payment_create_get_and_list_for_student(db_session: Session) -> None:
    student = StudentRepo(db_session).create(_make_student())
    repo = PaymentRepo(db_session)
    p2 = repo.create(_make_payment(student.id, cycle_number=2))
    p1 = repo.create(_make_payment(student.id, cycle_number=1))

    assert repo.get(p1.id) is p1
    # list_for_student is ordered by cycle_number
    assert [p.cycle_number for p in repo.list_for_student(student.id)] == [1, 2]
    assert {p2, p1} == set(repo.list_for_student(student.id))


def test_payment_get_by_student_cycle(db_session: Session) -> None:
    student = StudentRepo(db_session).create(_make_student())
    repo = PaymentRepo(db_session)
    assert repo.get_by_student_cycle(student.id, 1) is None
    created = repo.create(_make_payment(student.id, cycle_number=1))
    assert repo.get_by_student_cycle(student.id, 1) is created


def test_payment_bulk_create(db_session: Session) -> None:
    student = StudentRepo(db_session).create(_make_student())
    repo = PaymentRepo(db_session)
    payments = repo.bulk_create([_make_payment(student.id, cycle_number=c) for c in (1, 2, 3)])
    assert all(p.id is not None for p in payments)
    assert len(repo.list_for_student(student.id)) == 3


def test_payment_list_paid_between(db_session: Session) -> None:
    student = StudentRepo(db_session).create(_make_student())
    repo = PaymentRepo(db_session)
    for cycle, paid in ((1, date(2023, 4, 10)), (2, date(2023, 5, 3)), (3, date(2023, 5, 28))):
        p = _make_payment(student.id, cycle)
        p.paid_date = paid
        repo.create(p)
    # Half-open [May 1, June 1): only the two May payments.
    in_may = repo.list_paid_between(date(2023, 5, 1), date(2023, 6, 1))
    assert [p.paid_date for p in in_may] == [date(2023, 5, 3), date(2023, 5, 28)]


def test_payment_delete(db_session: Session) -> None:
    student = StudentRepo(db_session).create(_make_student())
    repo = PaymentRepo(db_session)
    payment = repo.create(_make_payment(student.id, cycle_number=1))
    repo.delete(payment)
    assert repo.get(payment.id) is None


# --------------------------------------------------------------------------- #
# OverrideRepo
# --------------------------------------------------------------------------- #


def test_override_create_and_list_for_student(db_session: Session) -> None:
    student = StudentRepo(db_session).create(_make_student())
    repo = OverrideRepo(db_session)
    created = repo.create(
        AnchorOverride(
            student_id=student.id,
            new_due_date=date(2023, 7, 20),
            reason="Agreed to shift to the 20th",
        )
    )
    assert created.id is not None
    assert repo.get(created.id) is created
    assert repo.list_for_student(student.id) == [created]


def test_override_delete(db_session: Session) -> None:
    student = StudentRepo(db_session).create(_make_student())
    repo = OverrideRepo(db_session)
    override = repo.create(
        AnchorOverride(student_id=student.id, new_due_date=date(2023, 7, 20), reason="shift")
    )
    repo.delete(override)
    assert repo.get(override.id) is None
