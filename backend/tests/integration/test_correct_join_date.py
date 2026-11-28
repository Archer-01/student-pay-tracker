"""Correcting a mistyped join date (decision 0015).

The join date is the anchor every due date is computed from. It can be corrected only while
nothing recorded depends on it: no payment, no moved due date, no write-off. A corrected student
then reads exactly as if the right date had been typed at enrolment; that is the property below.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from app.models import FreePeriod
from app.services.debt_service import DebtService
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import (
    DomainError,
    InvalidOverrideError,
    InvalidPeriodError,
    JoinDateLockedError,
)
from app.services.ledger_service import LedgerService
from app.services.override_service import OverrideService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

TYPED = date(2026, 9, 5)
RIGHT = date(2026, 10, 12)
ENTERED = date(2026, 10, 20)
AS_OF = date(2027, 3, 1)


def _enrol(session: Session, joined: date = TYPED, price: str = "300") -> int:
    return (
        StudentService(session)
        .enroll(first_name="Salma", join_date=joined, custom_price=Decimal(price), today=ENTERED)
        .id
    )


def _ledger(session: Session, sid: int) -> list[tuple[int, date, date | None, bool, bool]]:
    return [
        (e.cycle_number, e.expected_due_date, e.paid_date, e.suspended, e.waived)
        for e in LedgerService(session).get_ledger(sid, AS_OF)
    ]


def _summary(session: Session, sid: int) -> tuple[int, Decimal, int]:
    s = LedgerService(session).student_summary(sid, AS_OF)
    return s.months_overdue, s.amount_owed, s.cumulative_drift


def test_a_mistyped_join_date_can_be_corrected_while_nothing_is_recorded(
    db_session: Session,
) -> None:
    sid = _enrol(db_session)
    StudentService(db_session).update(sid, join_date=RIGHT, today=ENTERED)
    assert StudentService(db_session).get(sid).join_date == RIGHT
    assert _ledger(db_session, sid)[0][1] == RIGHT  # the first month falls due on the new date
    # The first attendance period starts on it too.
    assert EnrollmentService(db_session).history(sid)[0].entry_date == RIGHT


def test_aymens_case_payments_deleted_then_the_date_corrected(db_session: Session) -> None:
    sid = _enrol(db_session)
    payments = PaymentService(db_session)
    payments.record_payment(
        student_id=sid, cycle_number=0, paid_date=TYPED, amount=Decimal("300"), today=ENTERED
    )
    with pytest.raises(JoinDateLockedError) as exc:
        StudentService(db_session).update(sid, join_date=RIGHT, today=ENTERED)
    assert (exc.value.code, exc.value.params) == ("join_date_has_payments", {"count": 1})
    assert StudentService(db_session).get(sid).join_date == TYPED  # nothing moved

    payments.delete_payment(student_id=sid, cycle_number=0)
    StudentService(db_session).update(sid, join_date=RIGHT, today=ENTERED)
    assert StudentService(db_session).get(sid).join_date == RIGHT


def test_sending_the_same_date_with_payments_is_not_a_correction(db_session: Session) -> None:
    # The edit form sends every field: saving a phone number must not trip the lock.
    sid = _enrol(db_session)
    PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=0, paid_date=TYPED, amount=Decimal("300"), today=ENTERED
    )
    StudentService(db_session).update(sid, join_date=TYPED, phone="0600000000", today=ENTERED)
    assert StudentService(db_session).get(sid).phone == "0600000000"


def test_a_changed_payment_day_stays_and_the_join_date_is_corrected(db_session: Session) -> None:
    # « Changer le jour de paiement » is stored as a date, not from the join date: a student
    # corrected with it is a student enrolled right who had the same change.
    sid = _enrol(db_session)
    OverrideService(db_session).create_override(
        student_id=sid, new_due_date=date(2026, 10, 20), reason="paie le 20"
    )
    StudentService(db_session).update(sid, join_date=date(2026, 9, 25), today=ENTERED)
    dues = [e[1] for e in _ledger(db_session, sid)][:3]
    assert dues == [date(2026, 9, 25), date(2026, 10, 20), date(2026, 11, 20)]


def test_the_join_date_must_stay_before_a_changed_payment_day(db_session: Session) -> None:
    sid = _enrol(db_session)
    OverrideService(db_session).create_override(
        student_id=sid, new_due_date=date(2026, 10, 20), reason="paie le 20"
    )
    for too_late in (date(2026, 10, 20), date(2026, 10, 25)):
        with pytest.raises(JoinDateLockedError) as exc:
            StudentService(db_session).update(sid, join_date=too_late, today=ENTERED)
        assert (exc.value.code, exc.value.params) == (
            "join_date_after_payment_day",
            {"payment_day": date(2026, 10, 20)},
        )


def test_a_written_off_debt_locks_the_join_date(db_session: Session) -> None:
    sid = _enrol(db_session)
    EnrollmentService(db_session).leave(sid, leave_date=date(2026, 11, 10))
    DebtService(db_session).write_off(sid, reason="parti sans payer")
    with pytest.raises(JoinDateLockedError) as exc:
        StudentService(db_session).update(sid, join_date=date(2026, 9, 1), today=ENTERED)
    assert exc.value.code == "join_date_has_writeoffs"


def test_the_corrected_date_must_come_before_the_first_departure(db_session: Session) -> None:
    sid = _enrol(db_session)
    EnrollmentService(db_session).leave(sid, leave_date=date(2026, 10, 1))
    with pytest.raises(InvalidPeriodError) as exc:
        StudentService(db_session).update(sid, join_date=RIGHT, today=ENTERED)
    assert (exc.value.code, exc.value.params) == (
        "join_date_after_leave",
        {"leave_date": date(2026, 10, 1)},
    )


def test_a_free_period_from_joining_moves_with_the_date(db_session: Session) -> None:
    sid = _enrol(db_session, price="0")
    StudentService(db_session).update(sid, join_date=RIGHT, today=ENTERED)
    periods = db_session.query(FreePeriod).filter_by(student_id=sid).all()
    assert [(p.from_date, p.to_date) for p in periods] == [(RIGHT, None)]


def test_a_later_free_period_stays_where_it_is(db_session: Session) -> None:
    # Made free on a later day than joining: that day doesn't depend on the join date.
    sid = _enrol(db_session)
    StudentService(db_session).update(sid, custom_price=Decimal("0"), today=date(2026, 11, 3))
    StudentService(db_session).update(sid, join_date=RIGHT, today=date(2026, 11, 4))
    periods = db_session.query(FreePeriod).filter_by(student_id=sid).all()
    assert [(p.from_date, p.to_date) for p in periods] == [(date(2026, 11, 3), None)]


def test_a_stretch_made_free_later_on_the_typed_day_is_not_moved(db_session: Session) -> None:
    # Found by the domain review: join typed Nov 3 (meant Oct 25), made free on Nov 3 itself.
    # That stretch began on Nov 3, not "from joining", so it stays: Oct 25's month is owed.
    students = StudentService(db_session)
    sid = students.enroll(
        first_name="X", join_date=date(2026, 11, 3), custom_price=Decimal("300"), today=ENTERED
    ).id
    students.update(sid, custom_price=Decimal("0"), today=date(2026, 11, 3))
    students.update(sid, join_date=date(2026, 10, 25), today=date(2026, 11, 4))
    students.update(sid, custom_price=Decimal("300"), today=date(2026, 12, 1))
    periods = db_session.query(FreePeriod).filter_by(student_id=sid).all()
    assert [(p.from_date, p.to_date) for p in periods] == [(date(2026, 11, 3), date(2026, 12, 1))]
    assert _summary(db_session, sid)[:2] == (4, Decimal("1200"))  # Oct, Dec, Jan, Feb


def test_a_free_stretch_the_new_date_skips_entirely_is_dropped(db_session: Session) -> None:
    # Free from joining (Sep 5) until priced on Oct 1, then the date corrected to Oct 12: that
    # stretch is before the student was even there, so it no longer covers any day.
    students = StudentService(db_session)
    sid = students.enroll(
        first_name="Salma", join_date=TYPED, custom_price=Decimal("0"), today=TYPED
    ).id
    students.update(sid, custom_price=Decimal("300"), today=date(2026, 10, 1))
    assert db_session.query(FreePeriod).filter_by(student_id=sid).count() == 1
    students.update(sid, join_date=RIGHT, today=ENTERED)
    assert db_session.query(FreePeriod).filter_by(student_id=sid).all() == []


def test_attendance_not_starting_on_the_join_date_is_left_alone(db_session: Session) -> None:
    # Older data can hold a first period that doesn't start on the anchor: nothing to move.
    from app.models import EnrollmentPeriod

    sid = _enrol(db_session)
    first = db_session.query(EnrollmentPeriod).filter_by(student_id=sid).one()
    first.entry_date = date(2026, 9, 20)
    db_session.commit()
    StudentService(db_session).update(sid, join_date=RIGHT, today=ENTERED)
    assert EnrollmentService(db_session).history(sid)[0].entry_date == date(2026, 9, 20)


# --------------------------------------------------------------------------- #
# Property (drift-invariants): a corrected student is the student typed right
# --------------------------------------------------------------------------- #

BASE = date(2026, 9, 1)


def _view(session: Session, sid: int) -> tuple[object, ...]:
    ledger = LedgerService(session)
    entries = [
        (e.cycle_number, e.expected_due_date, e.paid_date, e.days_late, e.amount,
         e.cumulative_drift, e.suspended, e.waived)
        for e in ledger.get_ledger(sid, AS_OF)
    ]  # fmt: skip
    history = [(p.entry_date, p.leave_date) for p in EnrollmentService(session).history(sid)]
    return entries, _summary(session, sid), history


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    typed=st.integers(-120, 150),
    right=st.integers(-120, 150),
    price=st.sampled_from(["300", "0"]),
    flips_before=st.lists(st.integers(0, 40), max_size=2),
    correct_after=st.integers(0, 60),
    flips_after=st.lists(st.integers(1, 60), max_size=2),
    leave=st.one_of(st.none(), st.integers(0, 60)),
    back=st.one_of(st.none(), st.integers(0, 60)),
    pay=st.booleans(),
    payment_day=st.one_of(st.none(), st.integers(1, 90)),
)
def test_correcting_the_join_date_is_the_same_as_typing_it_right(
    db_session: Session,
    typed: int,
    right: int,
    price: str,
    flips_before: list[int],
    correct_after: int,
    flips_after: list[int],
    leave: int | None,
    back: int | None,
    pay: bool,
    payment_day: int | None,
) -> None:
    # Both students live the same history (price changes, a leave and a return, a payment), one
    # typed with the wrong date and corrected along the way: they must read the same.
    typed_on, right_on = BASE + timedelta(typed), BASE + timedelta(right)
    if typed_on > ENTERED:
        # A typed date in the future makes a free stretch closed before it cover no day, so it
        # is deleted and can't be brought back (decision 0015, Consequences).
        flips_before = []
    students = StudentService(db_session)
    fixed = students.enroll(
        first_name="F", join_date=typed_on, custom_price=Decimal(price), today=ENTERED
    ).id
    control = students.enroll(
        first_name="C", join_date=right_on, custom_price=Decimal(price), today=ENTERED
    ).id
    current, day = Decimal(price), ENTERED
    if payment_day is not None:
        # The same changed payment day for both, after both dates (as its own rule requires).
        moved_to = max(typed_on, right_on) + timedelta(payment_day)
        for sid in (fixed, control):
            OverrideService(db_session).create_override(
                student_id=sid, new_due_date=moved_to, reason="paie plus tard"
            )

    def flip(on: date) -> None:
        nonlocal current
        current = Decimal("300") if current == 0 else Decimal("0")
        for sid in (fixed, control):
            students.update(sid, custom_price=current, today=on)

    for offset in sorted(flips_before):
        day = ENTERED + timedelta(offset)
        flip(day)
    if leave is not None:
        left_on = max(typed_on, right_on) + timedelta(leave)
        for sid in (fixed, control):
            EnrollmentService(db_session).leave(sid, leave_date=left_on)
            if back is not None:
                EnrollmentService(db_session).return_(sid, entry_date=left_on + timedelta(back))
    day += timedelta(correct_after)
    students.update(fixed, join_date=right_on, today=day)
    for offset in sorted(flips_after):
        flip(day + timedelta(offset))
    if pay:
        outcomes: list[object] = []
        for sid in (fixed, control):
            try:
                p = PaymentService(db_session).record_payment(
                    student_id=sid,
                    cycle_number=0,
                    paid_date=right_on + timedelta(9),
                    amount=Decimal("300"),
                    today=AS_OF,
                )
                outcomes.append((p.expected_due_date, p.days_late))
            except DomainError as exc:
                db_session.rollback()
                outcomes.append(exc.code)
        assert outcomes[0] == outcomes[1]
    assert _view(db_session, fixed) == _view(db_session, control)


# Several changed payment days, month ends, and corrections either way: the correction goes
# through exactly when a student enrolled on the right date could have had the same changes, and
# then both read the same. (Ported from the domain review's scratch test.)
_ANCHORS = [date(2026, 10, 31), date(2026, 11, 30), date(2027, 1, 31), date(2026, 12, 1)]
_LATER_ENTERED = date(2027, 1, 20)


def _month_end(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


@settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    typed_base=st.sampled_from(_ANCHORS),
    typed_shift=st.integers(-40, 40),
    right_base=st.sampled_from(_ANCHORS),
    right_shift=st.integers(-40, 40),
    payment_days=st.lists(st.integers(-60, 120), max_size=4),
    month_ends=st.booleans(),
)
def test_a_correction_with_changed_payment_days_is_refused_exactly_when_it_must_be(
    db_session: Session,
    typed_base: date,
    typed_shift: int,
    right_base: date,
    right_shift: int,
    payment_days: list[int],
    month_ends: bool,
) -> None:
    typed = typed_base + timedelta(typed_shift)
    right = right_base + timedelta(right_shift)
    if typed == right:
        return
    students = StudentService(db_session)
    overrides = OverrideService(db_session)
    fixed = students.enroll(
        first_name="F", join_date=typed, custom_price=Decimal("300"), today=_LATER_ENTERED
    ).id
    days = [typed + timedelta(d) for d in payment_days]
    if month_ends:
        days = [_month_end(d) for d in days]
    made: list[date] = []
    for day in sorted(days, key=lambda d: (d.year, d.month)):
        try:
            overrides.create_override(student_id=fixed, new_due_date=day, reason="r")
            made.append(day)
        except InvalidOverrideError:
            db_session.rollback()
    control = students.enroll(
        first_name="C", join_date=right, custom_price=Decimal("300"), today=_LATER_ENTERED
    ).id
    control_could = True
    for day in made:
        try:
            overrides.create_override(student_id=control, new_due_date=day, reason="r")
        except InvalidOverrideError:
            db_session.rollback()
            control_could = False
            break
    try:
        students.update(fixed, join_date=right, today=_LATER_ENTERED)
        corrected = True
    except JoinDateLockedError as exc:
        db_session.rollback()
        assert exc.code == "join_date_after_payment_day"
        corrected = False
    assert corrected == control_could
    if corrected:
        as_of = date(2027, 9, 1)
        ledger = LedgerService(db_session)

        def reads(sid: int) -> tuple[object, ...]:
            s = ledger.student_summary(sid, as_of)
            rows = [(e.cycle_number, e.expected_due_date) for e in ledger.get_ledger(sid, as_of)]
            return rows, s.months_overdue, s.amount_owed, s.next_expected_date

        assert reads(fixed) == reads(control)
        for cycle in (0, 2):
            outcomes: list[object] = []
            for sid in (fixed, control):
                try:
                    p = PaymentService(db_session).record_payment(
                        student_id=sid,
                        cycle_number=cycle,
                        paid_date=right + timedelta(40),
                        amount=Decimal("300"),
                        today=as_of,
                    )
                    outcomes.append((p.expected_due_date, p.days_late))
                except DomainError as exc:
                    db_session.rollback()
                    outcomes.append(exc.code)
            assert outcomes[0] == outcomes[1]
