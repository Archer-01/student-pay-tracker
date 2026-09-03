"""Model constraint tests — every domain rule must be enforced at the database level.

Each violation must raise ``IntegrityError`` on flush, proving the constraint lives in the
schema (and therefore the migration), not just in Python.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AnchorOverride, Payment, Student, StudentStatus


def _student(session: Session, **overrides: object) -> Student:
    defaults: dict[str, object] = {
        "first_name": "Amina",
        "phone": "+212600000000",
        "join_date": date(2023, 3, 5),
    }
    defaults.update(overrides)
    student = Student(**defaults)
    session.add(student)
    session.flush()
    return student


def _payment(session: Session, student: Student, **overrides: object) -> Payment:
    defaults: dict[str, object] = {
        "student_id": student.id,
        "cycle_number": 1,
        "paid_date": date(2023, 4, 10),
        "expected_due_date": date(2023, 4, 5),
        "days_late": 5,
        "amount": Decimal("300.00"),
    }
    defaults.update(overrides)
    payment = Payment(**defaults)
    session.add(payment)
    session.flush()
    return payment


# --------------------------------------------------------------------------- #
# Student
# --------------------------------------------------------------------------- #


def test_student_can_be_created_with_defaults(db_session: Session) -> None:
    student = _student(db_session)
    assert student.id is not None
    assert student.status is StudentStatus.ACTIVE  # default
    assert student.created_at is not None


def test_student_name_is_not_null(db_session: Session) -> None:
    db_session.add(Student(join_date=date(2023, 3, 5), custom_price=Decimal("300.00")))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_student_join_date_is_not_null(db_session: Session) -> None:
    db_session.add(Student(first_name="Amina", custom_price=Decimal("300.00")))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_student_custom_price_may_be_zero_for_free_students(db_session: Session) -> None:
    # Free / scholarship students are real; an agreed price may be 0 (>= 0, not > 0).
    student = _student(db_session, custom_price=Decimal("0.00"))
    assert student.custom_price == Decimal("0.00")


def test_student_custom_price_cannot_be_negative(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        _student(db_session, custom_price=Decimal("-1.00"))


# --------------------------------------------------------------------------- #
# Payment
# --------------------------------------------------------------------------- #


def test_payment_can_be_created(db_session: Session) -> None:
    student = _student(db_session)
    payment = _payment(db_session, student)
    assert payment.id is not None
    assert payment.days_late == 5


def test_payment_days_late_may_be_negative_for_early_payment(db_session: Session) -> None:
    student = _student(db_session)
    payment = _payment(db_session, student, paid_date=date(2023, 4, 1), days_late=-4)
    assert payment.days_late == -4


def test_duplicate_payment_for_same_cycle_is_rejected(db_session: Session) -> None:
    student = _student(db_session)
    _payment(db_session, student, cycle_number=1)
    with pytest.raises(IntegrityError):
        _payment(db_session, student, cycle_number=1)


def test_payment_amount_cannot_be_negative(db_session: Session) -> None:
    student = _student(db_session)
    with pytest.raises(IntegrityError):
        _payment(db_session, student, amount=Decimal("-1.00"))


def test_payment_cycle_number_cannot_be_negative(db_session: Session) -> None:
    student = _student(db_session)
    with pytest.raises(IntegrityError):
        _payment(db_session, student, cycle_number=-1)


# --------------------------------------------------------------------------- #
# AnchorOverride
# --------------------------------------------------------------------------- #


def test_override_can_be_created(db_session: Session) -> None:
    student = _student(db_session)
    override = AnchorOverride(
        student_id=student.id,
        new_due_date=date(2023, 7, 20),
        reason="Agreed to shift due date to the 20th",
    )
    db_session.add(override)
    db_session.flush()
    assert override.id is not None
    assert override.created_at is not None


def test_override_reason_cannot_be_empty(db_session: Session) -> None:
    student = _student(db_session)
    db_session.add(AnchorOverride(student_id=student.id, new_due_date=date(2023, 7, 20), reason=""))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_override_reason_cannot_be_whitespace(db_session: Session) -> None:
    student = _student(db_session)
    db_session.add(
        AnchorOverride(student_id=student.id, new_due_date=date(2023, 7, 20), reason="   ")
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


# --------------------------------------------------------------------------- #
# Referential integrity — history is protected
# --------------------------------------------------------------------------- #


def test_deleting_student_with_payments_is_refused(db_session: Session) -> None:
    student = _student(db_session)
    _payment(db_session, student)
    db_session.delete(student)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_deleting_student_with_overrides_is_refused(db_session: Session) -> None:
    student = _student(db_session)
    db_session.add(
        AnchorOverride(student_id=student.id, new_due_date=date(2023, 7, 20), reason="shift")
    )
    db_session.flush()
    db_session.delete(student)
    with pytest.raises(IntegrityError):
        db_session.flush()
