"""Integration tests for LedgerService — the canonical scenario and mixed 12-cycle history."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.services.exceptions import StudentNotFoundError
from app.services.ledger_service import LedgerService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_FEE = Decimal("300.00")


def _enroll(db_session: Session, join_date: date = date(2023, 3, 5)) -> int:
    return (
        StudentService(db_session)
        .enroll(first_name="Amina", phone=None, join_date=join_date, custom_price=_FEE)
        .id
    )


def test_canonical_march_to_june_drift_is_15_through_service_layer(db_session: Session) -> None:
    # The Sprint 3 exit criterion: drive the canonical scenario end-to-end and get 15.
    sid = _enroll(db_session)
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
    assert ledger.cumulative_drift(sid, as_of=date(2023, 6, 10)) == 15
    assert ledger.get_ledger(sid, as_of=date(2023, 6, 10))[-1].cumulative_drift == 15


def test_ledger_shows_unpaid_cycles_as_gaps(db_session: Session) -> None:
    sid = _enroll(db_session)
    # Only cycle 1 paid (5 late); cycle 0 (enrollment month) and cycle 2 unpaid.
    PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 10), amount=_FEE
    )
    entries = LedgerService(db_session).get_ledger(sid, as_of=date(2023, 6, 30))
    by_cycle = {e.cycle_number: e for e in entries}

    assert by_cycle[0].paid_date is None and by_cycle[0].days_late is None  # gap
    assert by_cycle[1].paid_date == date(2023, 4, 10) and by_cycle[1].days_late == 5
    assert by_cycle[2].paid_date is None  # unpaid gap
    assert entries[-1].cumulative_drift == 5


def test_next_expected_and_student_summary(db_session: Session) -> None:
    sid = _enroll(db_session)  # join 2023-03-05
    PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=1, paid_date=date(2023, 4, 10), amount=_FEE
    )
    ledger = LedgerService(db_session)
    # Next due on/after mid-April is May 5.
    assert ledger.next_expected_date(sid, as_of=date(2023, 4, 20)) == date(2023, 5, 5)

    summary = ledger.student_summary(sid, as_of=date(2023, 6, 30))
    assert summary.cumulative_drift == 5
    assert summary.months_overdue == 3  # cycles 0/2/3 unpaid by Jun 30 (cycle 1 paid)
    assert summary.payments_count == 1
    assert summary.total_paid == _FEE
    assert summary.next_expected_date == date(2023, 7, 5)  # next due after today's as_of


def test_ledger_unknown_student_raises(db_session: Session) -> None:
    with pytest.raises(StudentNotFoundError):
        LedgerService(db_session).get_ledger(999, as_of=date(2023, 6, 30))
    with pytest.raises(StudentNotFoundError):
        LedgerService(db_session).cumulative_drift(999, as_of=date(2023, 6, 30))
    with pytest.raises(StudentNotFoundError):
        LedgerService(db_session).student_summary(999, as_of=date(2023, 6, 30))


def test_mixed_twelve_cycle_history(db_session: Session) -> None:
    sid = _enroll(db_session)
    payments = PaymentService(db_session)
    # Cycles 1..12: on-time (0 late) for odd cycles, 3 days late for even, skip cycle 7.
    expected_drift = 0
    for cycle in range(1, 13):
        if cycle == 7:
            continue  # skipped -> gap, contributes 0
        lateness = 0 if cycle % 2 == 1 else 3
        # The due date for this cycle is the 5th, `cycle` months after March 2023.
        month = 3 + cycle
        year = 2023 + (month - 1) // 12
        month = (month - 1) % 12 + 1
        paid = date(year, month, 5 + lateness)
        payments.record_payment(student_id=sid, cycle_number=cycle, paid_date=paid, amount=_FEE)
        expected_drift += lateness

    ledger = LedgerService(db_session)
    as_of = date(2024, 5, 31)  # well past cycle 12 (due 2024-03-05)
    assert ledger.cumulative_drift(sid, as_of) == expected_drift
    entries = ledger.get_ledger(sid, as_of)
    # cycle 7 present as a gap
    gap = next(e for e in entries if e.cycle_number == 7)
    assert gap.paid_date is None and gap.days_late is None
    assert entries[-1].cumulative_drift == expected_drift


def test_first_payment_date_is_derived(db_session: Session) -> None:
    """Derived from the payments, never stored — so correcting a payment can't desync it."""
    from app.services.payment_service import PaymentService

    student = StudentService(db_session).enroll(
        first_name="Amina", join_date=date(2023, 3, 5), custom_price=Decimal("300")
    )
    summary = LedgerService(db_session).student_summary(student.id, date(2023, 6, 30))
    assert summary.first_payment_date is None  # no payments yet

    payments = PaymentService(db_session)
    payments.record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=Decimal("300")
    )
    payments.record_payment(
        student_id=student.id, cycle_number=0, paid_date=date(2023, 3, 20), amount=Decimal("300")
    )
    summary = LedgerService(db_session).student_summary(student.id, date(2023, 6, 30))
    # The earliest payment, not the first one recorded.
    assert summary.first_payment_date == date(2023, 3, 20)
