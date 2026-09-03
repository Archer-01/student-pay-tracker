"""Enrollment periods: leaving, returning, and the invariants that keep history honest.

The anchor never moves. A period says when a student was *present*; the billing schedule is still
generated from ``join_date`` forever. That separation is what lets a returning student keep the
drift they had already accumulated instead of quietly resetting it.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import InvalidPeriodError, StudentNotFoundError
from app.services.ledger_service import LedgerService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_JOIN = date(2023, 3, 5)


def _student(session: Session, price: str = "300"):
    return StudentService(session).enroll(
        first_name="Amina", join_date=_JOIN, custom_price=Decimal(price)
    )


# --------------------------------------------------------------------------- #
# Enrolling opens a period
# --------------------------------------------------------------------------- #


def test_enrolling_opens_a_period_at_the_join_date(db_session: Session) -> None:
    student = _student(db_session)
    periods = EnrollmentService(db_session).history(student.id)
    assert len(periods) == 1
    assert periods[0].entry_date == _JOIN
    assert periods[0].leave_date is None


def test_a_new_student_is_attending(db_session: Session) -> None:
    student = _student(db_session)
    service = EnrollmentService(db_session)
    assert service.is_attending(student.id) is True
    assert student.status is StudentStatus.ACTIVE


# --------------------------------------------------------------------------- #
# Leaving
# --------------------------------------------------------------------------- #


def test_leaving_closes_the_open_period(db_session: Session) -> None:
    student = _student(db_session)
    service = EnrollmentService(db_session)
    period = service.leave(student.id, leave_date=date(2023, 6, 30), reason="moved away")
    assert period.leave_date == date(2023, 6, 30)
    assert period.leave_reason == "moved away"
    assert service.is_attending(student.id) is False


def test_leaving_marks_the_student_inactive(db_session: Session) -> None:
    student = _student(db_session)
    EnrollmentService(db_session).leave(student.id, leave_date=date(2023, 6, 30))
    assert student.status is StudentStatus.INACTIVE


def test_leaving_twice_is_rejected(db_session: Session) -> None:
    student = _student(db_session)
    service = EnrollmentService(db_session)
    service.leave(student.id, leave_date=date(2023, 6, 30))
    with pytest.raises(InvalidPeriodError) as exc:
        service.leave(student.id, leave_date=date(2023, 7, 30))
    assert exc.value.code == "period_not_open"


def test_leaving_before_entering_is_rejected(db_session: Session) -> None:
    student = _student(db_session)
    with pytest.raises(InvalidPeriodError) as exc:
        EnrollmentService(db_session).leave(student.id, leave_date=date(2023, 1, 1))
    assert exc.value.code == "leave_before_entry"


def test_leaving_on_the_entry_date_is_allowed(db_session: Session) -> None:
    """A student who signs up and immediately quits is a real, if sad, case."""
    student = _student(db_session)
    period = EnrollmentService(db_session).leave(student.id, leave_date=_JOIN)
    assert period.leave_date == _JOIN


# --------------------------------------------------------------------------- #
# Returning
# --------------------------------------------------------------------------- #


def test_returning_opens_a_new_period(db_session: Session) -> None:
    student = _student(db_session)
    service = EnrollmentService(db_session)
    service.leave(student.id, leave_date=date(2023, 6, 30))
    service.return_(student.id, entry_date=date(2023, 10, 1))
    history = service.history(student.id)
    assert [(p.entry_date, p.leave_date) for p in history] == [
        (_JOIN, date(2023, 6, 30)),
        (date(2023, 10, 1), None),
    ]
    assert student.status is StudentStatus.ACTIVE


def test_returning_never_moves_the_anchor(db_session: Session) -> None:
    """The whole point: a return must not reset the drift schedule."""
    student = _student(db_session)
    service = EnrollmentService(db_session)
    service.leave(student.id, leave_date=date(2023, 6, 30))
    service.return_(student.id, entry_date=date(2024, 1, 1))
    db_session.refresh(student)
    assert student.join_date == _JOIN


def test_returning_while_still_attending_is_rejected(db_session: Session) -> None:
    student = _student(db_session)
    with pytest.raises(InvalidPeriodError) as exc:
        EnrollmentService(db_session).return_(student.id, entry_date=date(2023, 10, 1))
    assert exc.value.code == "period_already_open"


def test_returning_before_leaving_is_rejected(db_session: Session) -> None:
    """Periods must not overlap; a return dated inside a previous period would do that."""
    student = _student(db_session)
    service = EnrollmentService(db_session)
    service.leave(student.id, leave_date=date(2023, 6, 30))
    with pytest.raises(InvalidPeriodError) as exc:
        service.return_(student.id, entry_date=date(2023, 5, 1))
    assert exc.value.code == "return_before_leave"


def test_returning_on_the_leave_date_is_allowed(db_session: Session) -> None:
    student = _student(db_session)
    service = EnrollmentService(db_session)
    service.leave(student.id, leave_date=date(2023, 6, 30))
    service.return_(student.id, entry_date=date(2023, 6, 30))
    assert service.is_attending(student.id) is True


def test_several_leave_return_cycles(db_session: Session) -> None:
    student = _student(db_session)
    service = EnrollmentService(db_session)
    for leave, back in (
        (date(2023, 6, 30), date(2023, 10, 1)),
        (date(2024, 1, 31), date(2024, 4, 1)),
    ):
        service.leave(student.id, leave_date=leave)
        service.return_(student.id, entry_date=back)
    assert len(service.history(student.id)) == 3
    assert service.is_attending(student.id) is True


def test_unknown_student_raises(db_session: Session) -> None:
    service = EnrollmentService(db_session)
    for call in (
        lambda: service.leave(999, leave_date=_JOIN),
        lambda: service.return_(999, entry_date=_JOIN),
        lambda: service.history(999),
    ):
        with pytest.raises(StudentNotFoundError):
            call()


# --------------------------------------------------------------------------- #
# Amending a mistyped date
# --------------------------------------------------------------------------- #


def test_amending_a_period(db_session: Session) -> None:
    student = _student(db_session)
    service = EnrollmentService(db_session)
    period = service.leave(student.id, leave_date=date(2023, 6, 30))
    service.amend(student.id, period.id, leave_date=date(2023, 7, 31))
    assert service.history(student.id)[0].leave_date == date(2023, 7, 31)


def test_amending_cannot_break_the_ordering(db_session: Session) -> None:
    student = _student(db_session)
    service = EnrollmentService(db_session)
    first = service.leave(student.id, leave_date=date(2023, 6, 30))
    service.return_(student.id, entry_date=date(2023, 10, 1))
    # Pushing the first departure past the second arrival would overlap the two periods.
    with pytest.raises(InvalidPeriodError) as exc:
        service.amend(student.id, first.id, leave_date=date(2023, 12, 1))
    assert exc.value.code == "periods_overlap"


def test_amending_cannot_move_the_first_entry_off_the_anchor(db_session: Session) -> None:
    """The first period starts at join_date by definition; moving it would fork the schedule."""
    student = _student(db_session)
    service = EnrollmentService(db_session)
    first = service.history(student.id)[0]
    with pytest.raises(InvalidPeriodError) as exc:
        service.amend(student.id, first.id, entry_date=date(2023, 5, 1))
    assert exc.value.code == "first_entry_is_the_anchor"


def test_amending_an_unknown_period_raises(db_session: Session) -> None:
    student = _student(db_session)
    with pytest.raises(InvalidPeriodError) as exc:
        EnrollmentService(db_session).amend(student.id, 999, leave_date=_JOIN)
    assert exc.value.code == "period_not_found"


# --------------------------------------------------------------------------- #
# What it does to the money
# --------------------------------------------------------------------------- #


def test_months_away_are_not_owed(db_session: Session) -> None:
    student = _student(db_session, price="300")
    service = EnrollmentService(db_session)
    service.leave(student.id, leave_date=date(2023, 5, 31))
    service.return_(student.id, entry_date=date(2023, 9, 1))

    # Cycles due Mar 5, Apr 5, May 5 (present), Jun/Jul/Aug (away), Sep 5, Oct 5 (present).
    summary = LedgerService(db_session).student_summary(student.id, date(2023, 10, 31))
    assert summary.months_overdue == 5
    assert summary.amount_owed == Decimal("1500")


def test_a_student_who_left_stops_accruing(db_session: Session) -> None:
    """An open-ended absence suspends everything after the departure, not just closed gaps."""
    student = _student(db_session, price="300")
    EnrollmentService(db_session).leave(student.id, leave_date=date(2023, 5, 31))
    summary = LedgerService(db_session).student_summary(student.id, date(2024, 6, 30))
    # Only Mar, Apr, May fell inside the period.
    assert summary.months_overdue == 3
    assert summary.amount_owed == Decimal("900")


def test_leaving_never_erases_drift_already_accrued(db_session: Session) -> None:
    """Suspension stops *future* accrual; it must not subtract what already happened."""
    student = _student(db_session)
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 20), amount=Decimal("300")
    )
    ledger = LedgerService(db_session)
    before = ledger.cumulative_drift(student.id, date(2024, 6, 30))
    assert before == 15

    EnrollmentService(db_session).leave(student.id, leave_date=date(2023, 5, 31))
    assert ledger.cumulative_drift(student.id, date(2024, 6, 30)) == before


def test_a_returning_student_keeps_their_debt(db_session: Session) -> None:
    student = _student(db_session, price="300")
    service = EnrollmentService(db_session)
    # Owes March, April, May; leaves; comes back.
    service.leave(student.id, leave_date=date(2023, 5, 31))
    owed_at_leave = LedgerService(db_session).student_summary(
        student.id, date(2023, 5, 31)
    ).amount_owed
    service.return_(student.id, entry_date=date(2024, 1, 1))
    after = LedgerService(db_session).student_summary(student.id, date(2024, 1, 31))
    assert after.amount_owed >= owed_at_leave  # the old debt survives the absence


def test_a_paid_cycle_inside_a_gap_still_counts(db_session: Session) -> None:
    """Recorded payments are frozen truth: settling a month keeps it out of suspension."""
    student = _student(db_session)
    payments = PaymentService(db_session)
    # Cycle 3 is due 2023-06-05, inside the gap below, but was actually paid — late.
    payments.record_payment(
        student_id=student.id, cycle_number=3, paid_date=date(2023, 6, 25), amount=Decimal("300")
    )
    service = EnrollmentService(db_session)
    service.leave(student.id, leave_date=date(2023, 5, 31))
    service.return_(student.id, entry_date=date(2023, 9, 1))

    entries = {e.cycle_number: e for e in LedgerService(db_session).get_ledger(
        student.id, date(2023, 10, 31)
    )}
    assert entries[3].suspended is False
    assert entries[3].days_late == 20
    assert LedgerService(db_session).cumulative_drift(student.id, date(2023, 10, 31)) == 20


def test_suspended_cycles_are_visible_in_the_ledger(db_session: Session) -> None:
    """Shown as "away" rather than hidden — an absence is information, not a gap."""
    student = _student(db_session)
    service = EnrollmentService(db_session)
    service.leave(student.id, leave_date=date(2023, 5, 31))
    service.return_(student.id, entry_date=date(2023, 9, 1))
    entries = LedgerService(db_session).get_ledger(student.id, date(2023, 10, 31))
    suspended = [e.cycle_number for e in entries if e.suspended]
    assert suspended == [3, 4, 5]  # Jun, Jul, Aug
    assert all(e.cumulative_drift == 0 for e in entries)


def test_no_absence_means_nothing_is_suspended(db_session: Session) -> None:
    student = _student(db_session)
    entries = LedgerService(db_session).get_ledger(student.id, date(2024, 6, 30))
    assert all(e.suspended is False for e in entries)


def test_amending_a_later_period_entry_date(db_session: Session) -> None:
    """Only the *first* entry is pinned to the anchor; a later return may be corrected."""
    student = _student(db_session)
    service = EnrollmentService(db_session)
    service.leave(student.id, leave_date=date(2023, 6, 30))
    second = service.return_(student.id, entry_date=date(2023, 10, 1))
    service.amend(student.id, second.id, entry_date=date(2023, 9, 1))
    assert service.history(student.id)[1].entry_date == date(2023, 9, 1)


def test_amending_the_first_entry_to_the_anchor_is_a_no_op(db_session: Session) -> None:
    student = _student(db_session)
    service = EnrollmentService(db_session)
    first = service.history(student.id)[0]
    service.amend(student.id, first.id, entry_date=_JOIN)
    assert service.history(student.id)[0].entry_date == _JOIN


def test_amending_the_reason(db_session: Session) -> None:
    student = _student(db_session)
    service = EnrollmentService(db_session)
    period = service.leave(student.id, leave_date=date(2023, 6, 30), reason="typo")
    service.amend(student.id, period.id, reason="moved away")
    assert service.history(student.id)[0].leave_reason == "moved away"


def test_amending_cannot_invert_a_period(db_session: Session) -> None:
    """Pushing a departure before its own arrival is caught by the re-validation."""
    student = _student(db_session)
    service = EnrollmentService(db_session)
    service.leave(student.id, leave_date=date(2023, 6, 30))
    second = service.return_(student.id, entry_date=date(2023, 10, 1))
    with pytest.raises(InvalidPeriodError) as exc:
        service.amend(student.id, second.id, leave_date=date(2023, 9, 1))
    assert exc.value.code == "leave_before_entry"


def test_amending_a_period_of_another_student_raises(db_session: Session) -> None:
    first = _student(db_session)
    second = StudentService(db_session).enroll(first_name="Other", join_date=_JOIN)
    period = EnrollmentService(db_session).history(second.id)[0]
    with pytest.raises(InvalidPeriodError) as exc:
        EnrollmentService(db_session).amend(first.id, period.id, reason="x")
    assert exc.value.code == "period_not_found"


def test_a_student_with_no_recorded_periods_is_billed_normally(db_session: Session) -> None:
    """The pre-sprint-12 state: no attendance history means nothing is suspended."""
    from app.models import EnrollmentPeriod

    student = _student(db_session)
    for period in db_session.query(EnrollmentPeriod).all():
        db_session.delete(period)
    db_session.flush()
    entries = LedgerService(db_session).get_ledger(student.id, date(2024, 6, 30))
    assert entries and all(e.suspended is False for e in entries)
