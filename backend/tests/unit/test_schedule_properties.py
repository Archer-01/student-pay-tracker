"""Property-based tests for the drift domain core.

Per the ``drift-invariants`` skill these are non-negotiable: the failure modes of the
drift math are precisely the corner cases nobody thinks to write an example for. If any
of these ever finds a counterexample, pin that exact input as a permanent example test in
``test_schedule.py`` alongside the fix.
"""

from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from app.services.schedule import (
    Payment,
    add_months,
    cumulative_drift,
    generate_expected_due_dates,
)

# Bounded so ``add_months(join, cycle)`` stays comfortably within ``date`` range.
_JOIN_DATES = st.dates(min_value=date(2000, 1, 1), max_value=date(2030, 12, 31))
_AS_OF_DATES = st.dates(min_value=date(1990, 1, 1), max_value=date(2045, 12, 31))
_PAID_DATES = st.dates(min_value=date(1990, 1, 1), max_value=date(2045, 12, 31))
_CYCLE_NUMBERS = st.integers(min_value=0, max_value=120)

_PAYMENTS = st.lists(
    st.builds(Payment, cycle_number=_CYCLE_NUMBERS, paid_date=_PAID_DATES),
    max_size=12,
)


@given(join=_JOIN_DATES, payments=_PAYMENTS, a=_AS_OF_DATES, b=_AS_OF_DATES)
def test_drift_is_monotonic_non_decreasing_in_as_of(
    join: date, payments: list[Payment], a: date, b: date
) -> None:
    earlier, later = sorted((a, b))
    assert cumulative_drift(join, payments, earlier) <= cumulative_drift(join, payments, later)


@given(join=_JOIN_DATES, payments=_PAYMENTS, as_of=_AS_OF_DATES)
def test_drift_is_always_non_negative(join: date, payments: list[Payment], as_of: date) -> None:
    assert cumulative_drift(join, payments, as_of) >= 0


@given(
    join=_JOIN_DATES,
    cycles=st.lists(_CYCLE_NUMBERS, max_size=12),
    as_of=_AS_OF_DATES,
)
def test_drift_is_zero_when_every_payment_is_on_time(
    join: date, cycles: list[int], as_of: date
) -> None:
    # Each payment lands exactly on its cycle's expected due date.
    payments = [Payment(cycle_number=c, paid_date=add_months(join, c)) for c in cycles]
    assert cumulative_drift(join, payments, as_of) == 0


@given(
    join=_JOIN_DATES,
    payments=_PAYMENTS,
    new_paid=_PAID_DATES,
    as_of=_AS_OF_DATES,
)
def test_adding_a_payment_never_decreases_drift(
    join: date, payments: list[Payment], new_paid: date, as_of: date
) -> None:
    # Add a payment for a brand-new cycle (one not already present).
    used = {p.cycle_number for p in payments}
    new_cycle = max(used, default=-1) + 1
    before = cumulative_drift(join, payments, as_of)
    after = cumulative_drift(
        join, [*payments, Payment(cycle_number=new_cycle, paid_date=new_paid)], as_of
    )
    assert after >= before


# --------------------------------------------------------------------------- #
# Override regression — the whole point of the audit-log design.
# Adding an override never changes the expected due date of any cycle whose due
# date falls before the override's effective month, so it can never retroactively
# alter (and therefore never reduce) drift for those earlier cycles.
# --------------------------------------------------------------------------- #


@st.composite
def _schedule_with_extra_override(draw: st.DrawFn) -> tuple[date, list[date], date]:
    join = draw(st.dates(min_value=date(2000, 1, 1), max_value=date(2025, 12, 31)))
    # Distinct month-offsets from the anchor; day 1..28 to sidestep clamping ambiguity.
    offsets = draw(st.lists(st.integers(min_value=1, max_value=60), unique=True, max_size=5))
    days = draw(
        st.lists(
            st.integers(min_value=1, max_value=28), min_size=len(offsets), max_size=len(offsets)
        )
    )
    base = []
    for off, day in zip(offsets, days, strict=True):
        m = add_months(join, off)
        base.append(date(m.year, m.month, day))
    # The extra override's month is strictly after every base override's month.
    extra_off = draw(st.integers(min_value=max(offsets, default=0) + 1, max_value=120))
    em = add_months(join, extra_off)
    extra = date(em.year, em.month, draw(st.integers(min_value=1, max_value=28)))
    return join, base, extra


@given(_schedule_with_extra_override())
def test_override_never_changes_earlier_cycles(data: tuple[date, list[date], date]) -> None:
    join, base, extra = data
    up_to = add_months(join, 200)
    without = generate_expected_due_dates(join, up_to, base)
    with_extra = generate_expected_due_dates(join, up_to, [*base, extra])
    extra_month = (extra.year, extra.month)
    for a, b in zip(without, with_extra, strict=False):
        if (a.year, a.month) < extra_month:
            assert a == b
        else:
            break


@given(
    join=_JOIN_DATES,
    overrides=st.lists(_PAID_DATES, max_size=5),
)
def test_due_dates_are_strictly_increasing(join: date, overrides: list[date]) -> None:
    dues = generate_expected_due_dates(join, add_months(join, 120), overrides)
    assert all(a < b for a, b in zip(dues, dues[1:], strict=False))
