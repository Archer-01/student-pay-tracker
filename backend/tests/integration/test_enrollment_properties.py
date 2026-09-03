"""Property tests for enrollment periods: suspension must not corrupt drift or arrears.

These live in ``integration`` rather than ``unit`` because they exercise the *ledger*, which needs
a database. ``schedule.py`` is deliberately untouched by enrollment periods — the schedule is
still generated from the immutable anchor, and absence is a filter applied on top — so its own
pure property tests in ``tests/unit`` remain the guard for the math itself.

Per the ``drift-invariants`` skill: if any of these ever finds a counterexample, pin that exact
input as a permanent example test alongside the fix.
"""

from datetime import date, timedelta
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session

from app.services.enrollment_service import EnrollmentService
from app.services.ledger_service import LedgerService
from app.services.payment_service import PaymentService
from app.services.schedule import add_months
from app.services.student_service import StudentService

_ANCHOR = date(2023, 1, 10)

def _offsets(draw, count: int) -> list[int]:
    """Strictly increasing day offsets from the anchor, for building non-overlapping periods."""
    picks = draw(
        st.lists(st.integers(min_value=0, max_value=900), min_size=count, max_size=count,
                 unique=True)
    )
    return sorted(picks)


@st.composite
def _absences(draw) -> list[tuple[int, int]]:
    """Zero to three non-overlapping (leave, return) day-offset pairs, in order."""
    pairs = draw(st.integers(min_value=0, max_value=3))
    if pairs == 0:
        return []
    offsets = _offsets(draw, pairs * 2)
    return [(offsets[i * 2], offsets[i * 2 + 1]) for i in range(pairs)]


def _build(session: Session, absences: list[tuple[int, int]], paid_cycles: list[int]):
    student = StudentService(session).enroll(
        first_name="P", join_date=_ANCHOR, custom_price=Decimal("100")
    )
    payments = PaymentService(session)
    for cycle in sorted(set(paid_cycles)):
        due = _ANCHOR
        for _ in range(cycle):
            due = add_months(due, 1)
        payments.record_payment(
            student_id=student.id, cycle_number=cycle,
            paid_date=due + timedelta(days=cycle % 7), amount=Decimal("100"),
        )
    enrollment = EnrollmentService(session)
    for leave, back in absences:
        enrollment.leave(student.id, leave_date=_ANCHOR + timedelta(days=leave))
        enrollment.return_(student.id, entry_date=_ANCHOR + timedelta(days=back))
    return student


@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    absences=_absences(), paid=st.lists(st.integers(min_value=0, max_value=11), max_size=5)
)
def test_drift_is_non_decreasing_with_any_absences(
    db_session: Session, absences: list[tuple[int, int]], paid: list[int]
) -> None:
    """Property 1: cumulative drift never goes backwards as `as_of` advances, absences or not."""
    student = _build(db_session, absences, paid)
    ledger = LedgerService(db_session)
    seen = 0
    probe = _ANCHOR
    for _ in range(30):
        probe = add_months(probe, 1)
        current = ledger.cumulative_drift(student.id, probe)
        assert current >= seen
        seen = current


@settings(
    max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    absences=_absences(), paid=st.lists(st.integers(min_value=0, max_value=11), max_size=5)
)
def test_absences_never_increase_what_is_owed(
    db_session: Session, absences: list[tuple[int, int]], paid: list[int]
) -> None:
    """Property 2: recording an absence can only reduce arrears and drift, never add to them."""
    as_of = date(2025, 6, 30)
    baseline = _build(db_session, [], paid)
    ledger = LedgerService(db_session)
    base = ledger.student_summary(baseline.id, as_of)

    away = _build(db_session, absences, paid)
    after = ledger.student_summary(away.id, as_of)

    assert after.months_overdue <= base.months_overdue
    assert after.amount_owed <= base.amount_owed
    assert after.cumulative_drift == base.cumulative_drift  # drift comes from payments only


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(paid=st.lists(st.integers(min_value=0, max_value=11), max_size=5))
def test_one_open_period_is_a_strict_no_op(db_session: Session, paid: list[int]) -> None:
    """Property 3: a student who never left must produce exactly the pre-sprint ledger.

    This is the regression that protects every earlier sprint: enrollment periods must be
    invisible unless somebody actually leaves.
    """
    student = _build(db_session, [], paid)
    as_of = date(2025, 6, 30)
    entries = LedgerService(db_session).get_ledger(student.id, as_of)
    assert entries  # the scenario is not vacuous
    assert all(e.suspended is False for e in entries)
    summary = LedgerService(db_session).student_summary(student.id, as_of)
    assert summary.months_overdue == sum(1 for e in entries if e.paid_date is None)


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(
    gap=st.integers(min_value=0, max_value=800),
    paid=st.lists(st.integers(min_value=0, max_value=11), max_size=4),
)
def test_leaving_and_returning_the_same_day_changes_nothing(
    db_session: Session, gap: int, paid: list[int]
) -> None:
    """Property 4: a zero-length absence is indistinguishable from never having left."""
    as_of = date(2025, 6, 30)
    ledger = LedgerService(db_session)
    baseline = _build(db_session, [], paid)
    base = ledger.student_summary(baseline.id, as_of)

    same_day = _build(db_session, [(gap, gap)], paid)
    after = ledger.student_summary(same_day.id, as_of)

    assert (after.months_overdue, after.amount_owed, after.cumulative_drift) == (
        base.months_overdue, base.amount_owed, base.cumulative_drift,
    )
