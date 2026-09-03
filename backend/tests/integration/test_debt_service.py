"""Leavers with debt: who walked away owing money, and how that gets cleared.

The flag is **derived** — no open period, plus an outstanding balance as of the last departure —
so it clears itself the moment the money arrives. There are only two ways off the list: pay, or
have the balance written off with a reason.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.services.debt_service import DebtService
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import InvalidWriteoffError, StudentNotFoundError
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_JOIN = date(2023, 3, 5)


def _student(session: Session, first: str = "Amina", price: str = "300", **kw: object):
    return StudentService(session).enroll(
        first_name=first, join_date=_JOIN, custom_price=Decimal(price), **kw
    )


def _left_owing(session: Session, first: str = "Amina", leave: date = date(2023, 6, 30)):
    """A student who leaves with cycles 0..3 unpaid (Mar, Apr, May, Jun)."""
    student = _student(session, first)
    EnrollmentService(session).leave(student.id, leave_date=leave)
    return student


# --------------------------------------------------------------------------- #
# Who counts
# --------------------------------------------------------------------------- #


def test_a_student_still_attending_is_not_a_leaver(db_session: Session) -> None:
    student = _student(db_session)
    status = DebtService(db_session).status(student.id)
    assert status.left_with_debt is False
    assert status.left_on is None


def test_a_leaver_who_owes_nothing_is_not_flagged(db_session: Session) -> None:
    student = _student(db_session)
    payments = PaymentService(db_session)
    for cycle, day in enumerate(
        (date(2023, 3, 5), date(2023, 4, 5), date(2023, 5, 5), date(2023, 6, 5))
    ):
        payments.record_payment(
            student_id=student.id, cycle_number=cycle, paid_date=day, amount=Decimal("300")
        )
    EnrollmentService(db_session).leave(student.id, leave_date=date(2023, 6, 30))
    assert DebtService(db_session).status(student.id).left_with_debt is False


def test_a_leaver_who_owes_is_flagged_with_the_amount(db_session: Session) -> None:
    student = _left_owing(db_session)
    status = DebtService(db_session).status(student.id)
    assert status.left_with_debt is True
    assert status.left_on == date(2023, 6, 30)
    assert status.months_owed == 4  # Mar, Apr, May, Jun
    assert status.amount_owed == Decimal("1200")


def test_only_months_up_to_the_departure_count(db_session: Session) -> None:
    """Months after they left are suspended, so leaving caps the debt rather than growing it."""
    student = _left_owing(db_session, leave=date(2023, 4, 30))
    status = DebtService(db_session).status(student.id)
    assert status.months_owed == 2  # Mar and Apr only
    assert status.amount_owed == Decimal("600")


def test_a_student_who_left_and_came_back_is_not_a_leaver(db_session: Session) -> None:
    student = _left_owing(db_session)
    EnrollmentService(db_session).return_(student.id, entry_date=date(2023, 10, 1))
    assert DebtService(db_session).status(student.id).left_with_debt is False


def test_the_last_departure_is_the_one_that_counts(db_session: Session) -> None:
    student = _student(db_session)
    enrollment = EnrollmentService(db_session)
    enrollment.leave(student.id, leave_date=date(2023, 4, 30))
    enrollment.return_(student.id, entry_date=date(2023, 6, 1))
    enrollment.leave(student.id, leave_date=date(2023, 8, 31))
    assert DebtService(db_session).status(student.id).left_on == date(2023, 8, 31)


def test_paying_up_clears_the_flag_with_no_further_action(db_session: Session) -> None:
    """The main route off the list: record the money, and the derived flag resolves itself."""
    student = _left_owing(db_session)
    service = DebtService(db_session)
    assert service.status(student.id).left_with_debt is True

    payments = PaymentService(db_session)
    for cycle, day in enumerate(
        (date(2023, 7, 1), date(2023, 7, 1), date(2023, 7, 1), date(2023, 7, 1))
    ):
        payments.record_payment(
            student_id=student.id, cycle_number=cycle, paid_date=day, amount=Decimal("300")
        )
    assert service.status(student.id).left_with_debt is False


def test_an_unpriced_student_owes_nothing(db_session: Session) -> None:
    student = StudentService(db_session).enroll(first_name="Free", join_date=_JOIN)
    EnrollmentService(db_session).leave(student.id, leave_date=date(2023, 6, 30))
    assert DebtService(db_session).status(student.id).left_with_debt is False


# --------------------------------------------------------------------------- #
# The list
# --------------------------------------------------------------------------- #


def test_the_list_holds_only_leavers_who_owe(db_session: Session) -> None:
    _left_owing(db_session, "Owes")
    _student(db_session, "StillHere")
    paid = _student(db_session, "PaidUp")
    PaymentService(db_session).record_payment(
        student_id=paid.id, cycle_number=0, paid_date=_JOIN, amount=Decimal("300")
    )
    EnrollmentService(db_session).leave(paid.id, leave_date=_JOIN)

    listed = DebtService(db_session).leavers_with_debt()
    assert [s.student.full_name for s in listed] == ["Owes"]


def test_the_list_is_ordered_by_amount_owed(db_session: Session) -> None:
    small = _student(db_session, "Small", price="100")
    large = _student(db_session, "Large", price="900")
    enrollment = EnrollmentService(db_session)
    enrollment.leave(small.id, leave_date=date(2023, 6, 30))
    enrollment.leave(large.id, leave_date=date(2023, 6, 30))
    listed = DebtService(db_session).leavers_with_debt()
    assert [s.student.full_name for s in listed] == ["Large", "Small"]


def test_the_total_owed_across_leavers(db_session: Session) -> None:
    _left_owing(db_session, "A")
    _left_owing(db_session, "B")
    service = DebtService(db_session)
    assert service.total_owed() == Decimal("2400")


# --------------------------------------------------------------------------- #
# Writing a debt off
# --------------------------------------------------------------------------- #


def test_writing_off_clears_the_flag(db_session: Session) -> None:
    student = _left_owing(db_session)
    service = DebtService(db_session)
    writeoff = service.write_off(student.id, reason="parti à l'étranger")
    assert writeoff.amount == Decimal("1200")  # snapshot of what was forgiven
    status = service.status(student.id)
    assert status.left_with_debt is False
    assert status.written_off is not None


def test_a_write_off_needs_a_reason(db_session: Session) -> None:
    student = _left_owing(db_session)
    with pytest.raises(InvalidWriteoffError) as exc:
        DebtService(db_session).write_off(student.id, reason="   ")
    assert exc.value.code == "writeoff_reason_empty"


def test_cannot_write_off_a_student_who_owes_nothing(db_session: Session) -> None:
    student = _student(db_session)
    with pytest.raises(InvalidWriteoffError) as exc:
        DebtService(db_session).write_off(student.id, reason="x")
    assert exc.value.code == "nothing_to_write_off"


def test_a_write_off_is_not_a_payment(db_session: Session) -> None:
    """It must never look like money received: no payment row, no change to collected revenue."""
    from app.services.reports_service import ReportsService

    student = _left_owing(db_session)
    before = ReportsService(db_session).annual_report(2023).total_collected
    DebtService(db_session).write_off(student.id, reason="forgiven")
    assert ReportsService(db_session).annual_report(2023).total_collected == before
    assert student.payments == []


def test_a_write_off_does_not_touch_drift(db_session: Session) -> None:
    from app.services.ledger_service import LedgerService

    student = _left_owing(db_session)
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 20), amount=Decimal("300")
    )
    ledger = LedgerService(db_session)
    before = ledger.cumulative_drift(student.id, date(2024, 6, 30))
    DebtService(db_session).write_off(student.id, reason="forgiven")
    assert ledger.cumulative_drift(student.id, date(2024, 6, 30)) == before


def test_unknown_student_raises(db_session: Session) -> None:
    service = DebtService(db_session)
    with pytest.raises(StudentNotFoundError):
        service.status(999)
    with pytest.raises(StudentNotFoundError):
        service.write_off(999, reason="x")


# --------------------------------------------------------------------------- #
# The re-enrolment loophole
# --------------------------------------------------------------------------- #


def test_a_matching_phone_finds_a_past_leaver(db_session: Session) -> None:
    student = _student(db_session, "Amina")
    student.phone = "+212600112233"
    EnrollmentService(db_session).leave(student.id, leave_date=date(2023, 6, 30))
    matches = DebtService(db_session).similar_leavers(phone="+212600112233")
    assert [m.student.full_name for m in matches] == ["Amina"]


def test_a_matching_name_finds_a_past_leaver_case_and_accent_insensitively(
    db_session: Session,
) -> None:
    student = StudentService(db_session).enroll(
        first_name="Amïra", last_name="Benali", join_date=_JOIN, custom_price=Decimal("300")
    )
    EnrollmentService(db_session).leave(student.id, leave_date=date(2023, 6, 30))
    matches = DebtService(db_session).similar_leavers(first_name="amira", last_name="BENALI")
    assert len(matches) == 1


def test_only_leavers_who_owe_are_matched(db_session: Session) -> None:
    student = _student(db_session, "Amina")
    student.phone = "+212600112233"
    # Still attending, so not a leaver — no warning should be raised for them.
    assert DebtService(db_session).similar_leavers(phone="+212600112233") == []


def test_no_criteria_matches_nobody(db_session: Session) -> None:
    _left_owing(db_session)
    assert DebtService(db_session).similar_leavers() == []


def test_a_leaver_who_matches_neither_criterion_is_not_returned(db_session: Session) -> None:
    """Someone else's debt must not attach itself to a new student with a different name."""
    other = _student(db_session, "Youssef")
    other.phone = "+212611111111"
    EnrollmentService(db_session).leave(other.id, leave_date=date(2023, 6, 30))
    matches = DebtService(db_session).similar_leavers(
        phone="+212600000000", first_name="Amina", last_name="Benali"
    )
    assert matches == []
