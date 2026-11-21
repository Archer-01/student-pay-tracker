"""Integration tests for PaymentService.record_payment."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.services.exceptions import (
    DuplicatePaymentError,
    InvalidPaymentError,
    PaymentNotFoundError,
    StudentNotFoundError,
)
from app.services.override_service import OverrideService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService


def _student(db_session: Session, join_date: date = date(2023, 3, 5)) -> int:
    student = StudentService(db_session).enroll(
        first_name="Amina", phone=None, join_date=join_date, custom_price=Decimal("300.00")
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


# --------------------------------------------------------------------------- #
# The amount cap: a payment is never more than the student's monthly price
# --------------------------------------------------------------------------- #


def test_a_payment_above_the_monthly_price_is_rejected(db_session: Session) -> None:
    # The slip this exists for: 250 typed for a student whose agreed price is 200.
    sid = (
        StudentService(db_session)
        .enroll(
            first_name="Aymen", phone=None, join_date=date(2026, 9, 10), custom_price=Decimal("200")
        )
        .id
    )
    with pytest.raises(InvalidPaymentError) as exc:
        PaymentService(db_session).record_payment(
            student_id=sid, cycle_number=1, paid_date=date(2026, 10, 10), amount=Decimal("250")
        )
    assert exc.value.code == "payment_exceeds_price"
    assert exc.value.params == {"amount": Decimal("250.00"), "price": Decimal("200.00")}


def test_paying_exactly_the_price_or_less_is_fine(db_session: Session) -> None:
    # Less is normal: some students pay part of the month and owe the rest.
    sid = _student(db_session)  # price 300
    payments = PaymentService(db_session)
    payments.record_payment(
        student_id=sid, cycle_number=0, paid_date=date(2023, 3, 5), amount=Decimal("300")
    )
    payments.record_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 5), amount=Decimal("200")
    )


def test_a_student_without_a_price_has_no_cap(db_session: Session) -> None:
    # No pack and no agreed price: there is nothing to compare against.
    sid = (
        StudentService(db_session)
        .enroll(first_name="Omar", phone=None, join_date=date(2023, 3, 5))
        .id
    )
    payment = PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=0, paid_date=date(2023, 3, 5), amount=Decimal("450")
    )
    assert payment.amount == Decimal("450")


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-50")])
def test_a_payment_must_be_positive(db_session: Session, amount: Decimal) -> None:
    # The API schema already says so; the CLI goes straight to the service.
    sid = _student(db_session)
    with pytest.raises(InvalidPaymentError) as exc:
        PaymentService(db_session).record_payment(
            student_id=sid, cycle_number=0, paid_date=date(2023, 3, 5), amount=amount
        )
    assert exc.value.code == "payment_amount_not_positive"


# --------------------------------------------------------------------------- #
# Corrections
# --------------------------------------------------------------------------- #


def _paid(db_session: Session) -> int:
    """A price-300 student whose April (cycle 1, due Apr 5) was paid 5 days late."""
    sid = _student(db_session)
    PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 10), amount=Decimal("300")
    )
    return sid


def test_correcting_the_amount_keeps_the_dates(db_session: Session) -> None:
    sid = _paid(db_session)
    payment = PaymentService(db_session).update_payment(
        student_id=sid, cycle_number=1, amount=Decimal("250")
    )
    assert payment.amount == Decimal("250")
    assert payment.paid_date == date(2023, 4, 10)
    assert payment.days_late == 5


def test_correcting_the_paid_date_re_derives_lateness_from_the_frozen_due_date(
    db_session: Session,
) -> None:
    # An override recorded after the payment moves the live schedule, but the payment's own due
    # date stays frozen: a corrected paid date is measured against what was due *then*.
    sid = _paid(db_session)
    OverrideService(db_session).create_override(
        student_id=sid, new_due_date=date(2023, 5, 20), reason="moved"
    )
    payment = PaymentService(db_session).update_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 7)
    )
    assert payment.expected_due_date == date(2023, 4, 5)
    assert payment.days_late == 2
    assert payment.amount == Decimal("300")


def test_a_correction_obeys_the_same_cap(db_session: Session) -> None:
    sid = _paid(db_session)
    with pytest.raises(InvalidPaymentError) as exc:
        PaymentService(db_session).update_payment(
            student_id=sid, cycle_number=1, amount=Decimal("350")
        )
    assert exc.value.code == "payment_exceeds_price"


def test_correcting_only_the_date_does_not_recheck_an_old_amount(db_session: Session) -> None:
    # Pricing is current, not historical: if the price later drops below what was genuinely
    # paid, fixing that payment's date must not be blocked by an amount nobody is changing.
    sid = _paid(db_session)
    StudentService(db_session).update(sid, custom_price=Decimal("200"))
    payment = PaymentService(db_session).update_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 6)
    )
    assert payment.amount == Decimal("300")


def test_resending_the_same_amount_with_a_new_date_is_not_rechecked(db_session: Session) -> None:
    # A caller that sends every field (the CLI, a script) repeats the amount unchanged: that is
    # not "changing" it, so a later price cut must not block the date fix either.
    sid = _paid(db_session)
    StudentService(db_session).update(sid, custom_price=Decimal("200"))
    payment = PaymentService(db_session).update_payment(
        student_id=sid, cycle_number=1, amount=Decimal("300.00"), paid_date=date(2023, 4, 6)
    )
    assert payment.amount == Decimal("300")
    assert payment.paid_date == date(2023, 4, 6)


def test_correcting_a_missing_payment_errors(db_session: Session) -> None:
    sid = _student(db_session)
    with pytest.raises(PaymentNotFoundError):
        PaymentService(db_session).update_payment(
            student_id=sid, cycle_number=4, amount=Decimal("100")
        )


def test_correcting_for_an_unknown_student_errors(db_session: Session) -> None:
    with pytest.raises(StudentNotFoundError):
        PaymentService(db_session).update_payment(
            student_id=999, cycle_number=0, amount=Decimal("100")
        )


def test_deleting_a_payment_frees_its_cycle(db_session: Session) -> None:
    # The way to move a payment recorded against the wrong month: delete, then record again.
    sid = _paid(db_session)
    payments = PaymentService(db_session)
    payments.delete_payment(student_id=sid, cycle_number=1)
    with pytest.raises(PaymentNotFoundError):
        payments.get_payment(student_id=sid, cycle_number=1)
    payments.record_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 5), amount=Decimal("300")
    )


def test_deleting_a_missing_payment_errors(db_session: Session) -> None:
    sid = _student(db_session)
    with pytest.raises(PaymentNotFoundError):
        PaymentService(db_session).delete_payment(student_id=sid, cycle_number=0)
