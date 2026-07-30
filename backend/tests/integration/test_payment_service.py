"""Integration tests for PaymentService.record_payment."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.services.exceptions import DuplicatePaymentError, StudentNotFoundError
from app.services.override_service import OverrideService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService


def _student(db_session: Session, join_date: date = date(2023, 3, 5)) -> int:
    student = StudentService(db_session).enroll(
        name="Amina", phone=None, join_date=join_date, fee=Decimal("300.00")
    )
    return student.id


def test_record_on_time_payment(db_session: Session) -> None:
    sid = _student(db_session)
    payment = PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 5), amount=Decimal("300.00")
    )
    assert payment.expected_due_date == date(2023, 4, 5)
    assert payment.days_late == 0


def test_record_late_payment_freezes_days_late(db_session: Session) -> None:
    sid = _student(db_session)
    payment = PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 10), amount=Decimal("300.00")
    )
    assert payment.expected_due_date == date(2023, 4, 5)
    assert payment.days_late == 5


def test_record_early_payment_has_negative_days_late(db_session: Session) -> None:
    sid = _student(db_session)
    payment = PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 1), amount=Decimal("300.00")
    )
    assert payment.days_late == -4


def test_record_for_unknown_student_raises(db_session: Session) -> None:
    with pytest.raises(StudentNotFoundError):
        PaymentService(db_session).record_payment(
            student_id=999, cycle_number=0, paid_date=date(2023, 3, 5), amount=Decimal("1")
        )


def test_duplicate_payment_rejected(db_session: Session) -> None:
    sid = _student(db_session)
    svc = PaymentService(db_session)
    svc.record_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 5), amount=Decimal("300.00")
    )
    with pytest.raises(DuplicatePaymentError):
        svc.record_payment(
            student_id=sid, cycle_number=1, paid_date=date(2023, 4, 20), amount=Decimal("300.00")
        )


def test_cycle_for_month_resolves_override_aware(db_session: Session) -> None:
    sid = _student(db_session)
    svc = PaymentService(db_session)
    assert svc.cycle_for_month(sid, 2023, 4) == 1  # join March -> April is cycle 1
    OverrideService(db_session).create_override(
        student_id=sid, new_due_date=date(2023, 7, 20), reason="shift"
    )
    assert svc.cycle_for_month(sid, 2023, 7) == 4


def test_cycle_for_month_unknown_student_raises(db_session: Session) -> None:
    with pytest.raises(StudentNotFoundError):
        PaymentService(db_session).cycle_for_month(999, 2023, 4)


def test_record_payment_is_override_aware(db_session: Session) -> None:
    # Override moves July's due date to the 20th; cycle 4 (July) is judged against Jul 20.
    sid = _student(db_session)
    OverrideService(db_session).create_override(
        student_id=sid, new_due_date=date(2023, 7, 20), reason="agreed to shift to the 20th"
    )
    payment = PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=4, paid_date=date(2023, 7, 25), amount=Decimal("300.00")
    )
    assert payment.expected_due_date == date(2023, 7, 20)
    assert payment.days_late == 5
