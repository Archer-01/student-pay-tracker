"""Months that fell due while a student was free stay free (decision 0014, `free_period`).

A student is free while their price is 0 on purpose. Each stretch of that is a free period, opened
when they become free and closed when they get a price (or lose it). An unpaid month due inside
a period is `waived` in the ledger, like `suspended` for an absence: not owed, never chased.
Months due outside every period are owed as before, so a 0 typed by mistake and fixed the same day
erases nothing. Paid months are never waived, so drift can't move; the property tests pin that,
per the ``drift-invariants`` skill.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from app.models import ClassLevel, FreePeriod
from app.services.dashboard_service import DashboardService
from app.services.debt_service import DebtService
from app.services.enrollment_service import EnrollmentService
from app.services.ledger_service import LedgerService
from app.services.pack_service import PackService
from app.services.payment_service import PaymentService
from app.services.schedule import add_months
from app.services.student_service import StudentService

JOINED = date(2026, 9, 5)  # dues on the 5th: Sep, Oct, Nov, Dec…


def _free(session: Session, first: str = "Imrane") -> int:
    return (
        StudentService(session)
        .enroll(first_name=first, join_date=JOINED, custom_price=Decimal("0"), today=JOINED)
        .id
    )


def _priced(session: Session, first: str = "Amina") -> int:
    return (
        StudentService(session)
        .enroll(first_name=first, join_date=JOINED, custom_price=Decimal("300"), today=JOINED)
        .id
    )


def _owed(session: Session, sid: int, as_of: date) -> tuple[int, Decimal]:
    summary = LedgerService(session).student_summary(sid, as_of)
    return summary.months_overdue, summary.amount_owed


def _periods(session: Session, sid: int) -> list[tuple[date, date | None]]:
    rows = session.query(FreePeriod).filter_by(student_id=sid).order_by(FreePeriod.from_date)
    return [(p.from_date, p.to_date) for p in rows]


# --------------------------------------------------------------------------- #
# Free, then priced
# --------------------------------------------------------------------------- #


def test_a_student_enrolled_free_is_free_from_the_day_they_joined(db_session: Session) -> None:
    sid = _free(db_session)
    assert _periods(db_session, sid) == [(JOINED, None)]


def test_a_student_always_free_never_owes_anything(db_session: Session) -> None:
    sid = _free(db_session)
    assert _owed(db_session, sid, date(2028, 6, 1)) == (0, Decimal("0"))
    entries = LedgerService(db_session).get_ledger(sid, date(2027, 1, 10))
    assert all(e.waived for e in entries)


def test_pricing_a_free_student_bills_from_that_day_not_before(db_session: Session) -> None:
    sid = _free(db_session)
    StudentService(db_session).update(sid, custom_price=Decimal("300"), today=date(2026, 12, 10))
    assert _periods(db_session, sid) == [(JOINED, date(2026, 12, 10))]

    # September to December fell due while free: nothing owed for them.
    assert _owed(db_session, sid, date(2026, 12, 10)) == (0, Decimal("0"))
    # January is the first month due since the price: owed.
    assert _owed(db_session, sid, date(2027, 1, 10)) == (1, Decimal("300"))
    entries = LedgerService(db_session).get_ledger(sid, date(2027, 1, 10))
    assert [(e.expected_due_date.month, e.waived) for e in entries] == [
        (9, True), (10, True), (11, True), (12, True), (1, False),
    ]  # fmt: skip


def test_a_month_due_on_the_day_of_the_price_is_owed(db_session: Session) -> None:
    sid = _free(db_session)
    StudentService(db_session).update(sid, custom_price=Decimal("300"), today=date(2026, 12, 5))
    assert _owed(db_session, sid, date(2026, 12, 5)) == (1, Decimal("300"))


def test_a_student_with_no_price_yet_is_billed_back_once_priced(db_session: Session) -> None:
    # "unset" is a student nobody priced yet, not one free on purpose: their months are owed.
    sid = StudentService(db_session).enroll(first_name="Unset", join_date=JOINED).id
    StudentService(db_session).update(sid, custom_price=Decimal("300"), today=date(2026, 12, 10))
    assert _periods(db_session, sid) == []
    assert _owed(db_session, sid, date(2026, 12, 10)) == (4, Decimal("1200"))


def test_other_edits_leave_the_free_periods_alone(db_session: Session) -> None:
    students = StudentService(db_session)
    sid = _free(db_session)
    students.update(sid, custom_price=Decimal("300"), today=date(2026, 12, 10))
    students.update(sid, note="paie le samedi", today=date(2027, 3, 1))
    students.update(sid, custom_price=Decimal("250"), today=date(2027, 3, 1))  # priced to priced
    assert _periods(db_session, sid) == [(JOINED, date(2026, 12, 10))]


# --------------------------------------------------------------------------- #
# The cases the domain review found (kept as permanent regressions)
# --------------------------------------------------------------------------- #


def test_a_zero_typed_by_mistake_and_fixed_the_same_day_erases_no_debt(
    db_session: Session,
) -> None:
    sid = _priced(db_session)
    as_of = date(2026, 11, 20)
    assert _owed(db_session, sid, as_of) == (3, Decimal("900"))
    students = StudentService(db_session)
    students.update(sid, custom_price=Decimal("0"), today=as_of)
    students.update(sid, custom_price=Decimal("300"), today=as_of)
    assert _owed(db_session, sid, as_of) == (3, Decimal("900"))
    assert _periods(db_session, sid) == []  # a period of no days isn't kept


@pytest.mark.parametrize("on_a_free_pack", [False, True], ids=["agreed 0", "free pack"])
def test_an_enrolment_at_zero_fixed_the_same_day_erases_no_debt(
    db_session: Session, on_a_free_pack: bool
) -> None:
    # Enrolled today, joined in September: a mistaken 0 (or the wrong pack) fixed a minute later
    # must leave the September to November dues owed, as for a student enrolled at 300.
    today = date(2026, 11, 22)
    students = StudentService(db_session)
    if on_a_free_pack:
        offert = PackService(db_session).create(
            name="Offert", level=ClassLevel.TC, price=Decimal("0"), subjects=["Maths"]
        )
        sid = students.enroll(first_name="X", join_date=JOINED, pack_id=offert.id, today=today).id
    else:
        sid = students.enroll(
            first_name="X", join_date=JOINED, custom_price=Decimal("0"), today=today
        ).id
    students.update(sid, custom_price=Decimal("300"), today=today)
    assert _owed(db_session, sid, today) == (3, Decimal("900"))
    assert _periods(db_session, sid) == []


def test_a_price_corrected_to_zero_on_the_day_of_enrolment_frees_from_joining(
    db_session: Session,
) -> None:
    # Found by the property below: entered at 300 by mistake, fixed to 0 a minute later, is the
    # same student as one entered at 0, free since joining.
    entered = date(2026, 11, 22)
    students = StudentService(db_session)
    sid = students.enroll(
        first_name="X", join_date=JOINED, custom_price=Decimal("300"), today=entered
    ).id
    students.update(sid, custom_price=Decimal("0"), today=entered)
    assert _periods(db_session, sid) == [(JOINED, None)]
    # Made free on a later day instead, they owe the months before it once priced again.
    later = (
        StudentService(db_session)
        .enroll(first_name="Y", join_date=JOINED, custom_price=Decimal("300"), today=entered)
        .id
    )
    students.update(later, custom_price=Decimal("0"), today=date(2026, 11, 23))
    assert _periods(db_session, later) == [(date(2026, 11, 23), None)]


def test_a_free_period_opened_earlier_and_closed_later_is_kept(db_session: Session) -> None:
    # Enrolled free (backdated) on one day, priced on a later one: the months were free.
    students = StudentService(db_session)
    sid = students.enroll(
        first_name="X", join_date=JOINED, custom_price=Decimal("0"), today=date(2026, 11, 1)
    ).id
    students.update(sid, custom_price=Decimal("300"), today=date(2026, 11, 2))
    assert _periods(db_session, sid) == [(JOINED, date(2026, 11, 2))]
    # September and October stay free; November 5 fell due after the price, so it is owed.
    assert _owed(db_session, sid, date(2026, 11, 22)) == (1, Decimal("300"))


def test_a_leavers_debt_survives_a_price_set_to_zero_and_back(db_session: Session) -> None:
    sid = _priced(db_session)
    EnrollmentService(db_session).leave(sid, leave_date=date(2026, 11, 15))
    students = StudentService(db_session)
    students.update(sid, custom_price=Decimal("0"), today=date(2026, 11, 20))
    students.update(sid, custom_price=Decimal("300"), today=date(2026, 11, 20))
    assert [s.student.id for s in DebtService(db_session).leavers_with_debt()] == [sid]


def test_free_again_then_priced_again_waives_only_the_free_stretches(db_session: Session) -> None:
    students = StudentService(db_session)
    sid = _free(db_session)
    students.update(sid, custom_price=Decimal("300"), today=date(2026, 10, 10))
    students.update(sid, custom_price=Decimal("0"), today=date(2026, 11, 10))
    students.update(sid, custom_price=Decimal("300"), today=date(2027, 1, 10))
    assert _periods(db_session, sid) == [
        (JOINED, date(2026, 10, 10)),
        (date(2026, 11, 10), date(2027, 1, 10)),
    ]
    entries = LedgerService(db_session).get_ledger(sid, date(2027, 2, 10))
    # Sep and Oct free; Nov 5 fell due while priced (owed); Dec and Jan free; Feb owed.
    assert [(e.expected_due_date.month, e.waived) for e in entries] == [
        (9, True), (10, True), (11, False), (12, True), (1, True), (2, False),
    ]  # fmt: skip
    assert _owed(db_session, sid, date(2027, 2, 10)) == (2, Decimal("600"))


def test_free_then_no_price_then_a_price_keeps_the_free_months_free(db_session: Session) -> None:
    # Two saves: the agreed 0 cleared (no pack, so "no price"), then a pack chosen later.
    students = StudentService(db_session)
    sid = _free(db_session)
    students.update(sid, custom_price=None, today=date(2026, 12, 1))
    pack = PackService(db_session).create(
        name="Pack", level=ClassLevel.TC, price=Decimal("200"), subjects=["Maths"]
    )
    students.update(sid, pack_id=pack.id, today=date(2026, 12, 10))
    # Sep–Nov fell due while free; Dec 5 fell due with no price set, so it is owed once priced.
    assert _periods(db_session, sid) == [(JOINED, date(2026, 12, 1))]
    assert _owed(db_session, sid, date(2026, 12, 10)) == (1, Decimal("200"))


def test_a_free_pack_given_a_price_bills_its_students_from_that_day(db_session: Session) -> None:
    packs = PackService(db_session)
    pack = packs.create(name="Offert", level=ClassLevel.TC, price=Decimal("0"), subjects=["Maths"])
    on_pack = StudentService(db_session).enroll(first_name="P", join_date=JOINED, pack_id=pack.id)
    agreed = StudentService(db_session).enroll(
        first_name="A", join_date=JOINED, pack_id=pack.id, custom_price=Decimal("150")
    )
    packs.update(pack.id, price=Decimal("200"), today=date(2026, 12, 10))
    assert _periods(db_session, on_pack.id) == [(JOINED, date(2026, 12, 10))]
    assert _owed(db_session, on_pack.id, date(2026, 12, 10)) == (0, Decimal("0"))
    assert _owed(db_session, on_pack.id, date(2027, 1, 10)) == (1, Decimal("200"))
    # An agreed price wins over the pack's: that student was never free.
    assert _periods(db_session, agreed.id) == []


def test_a_pack_made_free_frees_its_students_from_that_day(db_session: Session) -> None:
    packs = PackService(db_session)
    pack = packs.create(name="Pack", level=ClassLevel.TC, price=Decimal("200"), subjects=["Maths"])
    sid = StudentService(db_session).enroll(first_name="P", join_date=JOINED, pack_id=pack.id).id
    packs.update(pack.id, price=Decimal("0"), today=date(2026, 11, 20))
    assert _periods(db_session, sid) == [(date(2026, 11, 20), None)]


def test_months_that_were_free_are_never_chased(db_session: Session) -> None:
    sid = _free(db_session)
    StudentService(db_session).update(sid, custom_price=Decimal("300"), today=date(2026, 12, 10))
    summary = DashboardService(db_session).get_summary(as_of=date(2026, 12, 20))
    assert summary.top_debtors == []
    assert summary.due_this_week == []
    assert summary.this_month.students_expected == 0


def test_a_paid_month_is_never_waived(db_session: Session) -> None:
    students = StudentService(db_session)
    sid = _priced(db_session, "Paid")
    PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=0, paid_date=date(2026, 9, 15), amount=Decimal("300")
    )
    students.update(sid, custom_price=Decimal("0"), today=date(2026, 9, 6))
    students.update(sid, custom_price=Decimal("300"), today=date(2026, 12, 10))
    first = LedgerService(db_session).get_ledger(sid, date(2026, 12, 10))[0]
    assert (first.paid_date, first.waived, first.days_late) == (date(2026, 9, 15), False, 10)


# --------------------------------------------------------------------------- #
# Properties (drift-invariants): free periods never touch drift, only ever reduce what is
# owed, and waive exactly the unpaid months due inside them.
# --------------------------------------------------------------------------- #


def _with_payments(session: Session, paid: list[int]) -> int:
    student = StudentService(session).enroll(
        first_name="P", join_date=JOINED, custom_price=Decimal("100")
    )
    for cycle in sorted(set(paid)):
        due = add_months(JOINED, cycle)
        PaymentService(session).record_payment(
            student_id=student.id,
            cycle_number=cycle,
            paid_date=due + timedelta(days=cycle % 9),
            amount=Decimal("100"),
            today=date(2028, 1, 1),
        )
    return student.id


# Free stretches as (start, length) in days from JOINED; a length of None leaves it open.
_stretches = st.lists(
    st.tuples(st.integers(0, 500), st.one_of(st.none(), st.integers(1, 200))), max_size=3
)
Stretches = list[tuple[int, int | None]]


def _add_periods(
    session: Session, sid: int, stretches: Stretches
) -> list[tuple[date, date | None]]:
    """Non-overlapping periods from the drawn stretches (overlaps dropped), at most one open."""
    periods: list[tuple[date, date | None]] = []
    end = -1
    for start, length in sorted(stretches, key=lambda s: s[0]):
        if start <= end:
            continue
        stop = None if length is None else start + length
        to_date = None if stop is None else JOINED + timedelta(stop)
        periods.append((JOINED + timedelta(start), to_date))
        if stop is None:
            break
        end = stop
    for from_date, to_date in periods:
        session.add(
            FreePeriod(student_id=sid, from_date=from_date, to_date=to_date, opened_on=from_date)
        )
    session.commit()
    return periods


_SETTINGS = settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)


@_SETTINGS
@given(stretches=_stretches, paid=st.lists(st.integers(0, 11), max_size=6))
def test_free_periods_never_change_drift_and_never_add_to_what_is_owed(
    db_session: Session, stretches: Stretches, paid: list[int]
) -> None:
    as_of = date(2027, 9, 30)
    plain = _with_payments(db_session, paid)
    freed = _with_payments(db_session, paid)
    _add_periods(db_session, freed, stretches)

    ledger = LedgerService(db_session)
    before, after = ledger.student_summary(plain, as_of), ledger.student_summary(freed, as_of)
    assert after.cumulative_drift == before.cumulative_drift
    assert after.months_overdue <= before.months_overdue
    assert after.amount_owed <= before.amount_owed


@_SETTINGS
@given(stretches=_stretches, paid=st.lists(st.integers(0, 11), max_size=6))
def test_only_unpaid_months_due_inside_a_free_period_are_waived(
    db_session: Session, stretches: Stretches, paid: list[int]
) -> None:
    sid = _with_payments(db_session, paid)
    periods = _add_periods(db_session, sid, stretches)
    for e in LedgerService(db_session).get_ledger(sid, date(2027, 9, 30)):
        inside = any(
            start <= e.expected_due_date and (end is None or e.expected_due_date < end)
            for start, end in periods
        )
        assert e.waived is (e.paid_date is None and inside)


# Prices a student can be given: an agreed price, an agreed 0, or none at all (no pack: unset).
_PRICES = st.sampled_from(["300", "0", None])
# A history of price changes: the enrolment price, then (days later, new price) steps.
_history = st.tuples(_PRICES, st.lists(st.tuples(st.integers(1, 60), _PRICES), max_size=5))


def _price(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _replay(
    session: Session,
    first: str | None,
    steps: list[tuple[int, str | None]],
    *,
    detour: tuple[int, str | None] | None = None,
) -> int:
    """Enrol (backdated: joined JOINED, entered ENTERED) and apply the steps through the service.

    ``detour`` = (step index, price): just before that step (index 0 is the enrolment), on the
    same day, the price is set to that value first: a mistake corrected at once.
    """
    entered = JOINED + timedelta(days=40)
    students = StudentService(session)
    enrol_with = detour[1] if detour and detour[0] == 0 else first
    sid = students.enroll(
        first_name="P", join_date=JOINED, custom_price=_price(enrol_with), today=entered
    ).id
    if detour and detour[0] == 0:
        students.update(sid, custom_price=_price(first), today=entered)
    day = entered
    for index, (gap, value) in enumerate(steps, start=1):
        day += timedelta(days=gap)
        if detour and detour[0] == index:
            students.update(sid, custom_price=_price(detour[1]), today=day)
        students.update(sid, custom_price=_price(value), today=day)
    return sid


@_SETTINGS
@given(history=_history, where=st.integers(0, 5), mistake=_PRICES)
def test_a_price_mistake_undone_the_same_day_changes_nothing(
    db_session: Session,
    history: tuple[str | None, list[tuple[int, str | None]]],
    where: int,
    mistake: str | None,
) -> None:
    # Driven through the service, where periods are written: a slip fixed at once, anywhere in a
    # student's price history (enrolment included), leaves every month exactly as it was.
    first, steps = history
    detour = (min(where, len(steps)), mistake)
    plain = _replay(db_session, first, steps)
    slipped = _replay(db_session, first, steps, detour=detour)
    as_of = date(2027, 6, 30)
    ledger = LedgerService(db_session)

    def months(sid: int) -> list[tuple[int, bool]]:
        return [(e.cycle_number, e.waived) for e in ledger.get_ledger(sid, as_of)]

    assert months(slipped) == months(plain)
    assert _owed(db_session, slipped, as_of) == _owed(db_session, plain, as_of)
    for sid in (plain, slipped):
        periods = _periods(db_session, sid)
        assert sum(1 for _, end in periods if end is None) <= 1
        for (_, end), (start, _) in zip(periods, periods[1:], strict=False):
            assert end is not None and end <= start  # never overlapping
