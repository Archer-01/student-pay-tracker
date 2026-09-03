"""Integration tests for OverrideService, including the core audit-log regression."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.repos import PaymentRepo, StudentRepo
from app.services.exceptions import InvalidOverrideError, StudentNotFoundError
from app.services.ledger_service import LedgerService
from app.services.override_service import OverrideService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_FEE = Decimal("300.00")


def _enroll(db_session: Session, join_date: date = date(2023, 3, 5)) -> int:
    return (
        StudentService(db_session)
        .enroll(first_name="Amina", phone=None, join_date=join_date, custom_price=_FEE)
        .id
    )


def test_create_override_happy_path(db_session: Session) -> None:
    sid = _enroll(db_session)
    override = OverrideService(db_session).create_override(
        student_id=sid, new_due_date=date(2023, 7, 20), reason="Agreed to shift to the 20th"
    )
    assert override.id is not None
    assert override.new_due_date == date(2023, 7, 20)


def test_create_override_unknown_student(db_session: Session) -> None:
    with pytest.raises(StudentNotFoundError):
        OverrideService(db_session).create_override(
            student_id=999, new_due_date=date(2023, 7, 20), reason="x"
        )


@pytest.mark.parametrize("reason", ["", "   "])
def test_create_override_rejects_empty_reason(db_session: Session, reason: str) -> None:
    sid = _enroll(db_session)
    with pytest.raises(InvalidOverrideError):
        OverrideService(db_session).create_override(
            student_id=sid, new_due_date=date(2023, 7, 20), reason=reason
        )


def test_create_override_rejects_date_on_or_before_join(db_session: Session) -> None:
    sid = _enroll(db_session, join_date=date(2023, 3, 5))
    with pytest.raises(InvalidOverrideError):
        OverrideService(db_session).create_override(
            student_id=sid, new_due_date=date(2023, 3, 5), reason="same as join"
        )


def test_create_override_rejects_backward_reanchor(db_session: Session) -> None:
    sid = _enroll(db_session)
    svc = OverrideService(db_session)
    svc.create_override(student_id=sid, new_due_date=date(2023, 8, 20), reason="first")
    with pytest.raises(InvalidOverrideError):
        svc.create_override(student_id=sid, new_due_date=date(2023, 6, 20), reason="backward")


def test_same_month_reoverride_is_allowed(db_session: Session) -> None:
    sid = _enroll(db_session)
    svc = OverrideService(db_session)
    svc.create_override(student_id=sid, new_due_date=date(2023, 8, 10), reason="first")
    # Correcting within the same month is allowed (last-wins).
    second = svc.create_override(student_id=sid, new_due_date=date(2023, 8, 25), reason="fix")
    assert second.id is not None


def test_override_does_not_reduce_drift_for_earlier_cycles(db_session: Session) -> None:
    """The whole point of the audit-log design: an override never rewrites past drift."""
    sid = _enroll(db_session, join_date=date(2023, 3, 5))
    payments = PaymentService(db_session)
    payments.record_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 10), amount=_FEE
    )
    payments.record_payment(
        student_id=sid, cycle_number=2, paid_date=date(2023, 5, 10), amount=_FEE
    )
    payments.record_payment(
        student_id=sid, cycle_number=3, paid_date=date(2023, 6, 10), amount=_FEE
    )

    ledger = LedgerService(db_session)
    as_of = date(2023, 6, 30)
    drift_before = ledger.cumulative_drift(sid, as_of)
    assert drift_before == 15

    # Snapshot the frozen payment rows and the anchor.
    before_rows = {
        p.cycle_number: (p.expected_due_date, p.days_late)
        for p in PaymentRepo(db_session).list_for_student(sid)
    }
    join_before = StudentRepo(db_session).get(sid).join_date

    # Create an override effective well after all recorded cycles.
    OverrideService(db_session).create_override(
        student_id=sid, new_due_date=date(2023, 9, 20), reason="agreed new schedule"
    )

    # Drift for the earlier cycles is unchanged...
    assert ledger.cumulative_drift(sid, as_of) == drift_before
    # ...the anchor is untouched...
    assert StudentRepo(db_session).get(sid).join_date == join_before
    # ...and no existing payment row was mutated.
    after_rows = {
        p.cycle_number: (p.expected_due_date, p.days_late)
        for p in PaymentRepo(db_session).list_for_student(sid)
    }
    assert after_rows == before_rows
