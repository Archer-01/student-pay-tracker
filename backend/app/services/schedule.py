"""Drift domain core — pure functions, no DB, no FastAPI, no async.

This is the highest-value, highest-risk code in the repo: it decides, for a student
anchored to a ``join_date``, when each monthly payment is *due* and how much cumulative
lateness ("drift") has accrued.

Model (see the approved plans and the ``drift-invariants`` skill):

* The due schedule is fixed and anchored to the join day-of-month. ``join_date`` itself is
  cycle 0 (the enrollment month); cycle *n* is due ``n`` calendar months later.
* Calendar-month arithmetic preserves the anchor day and clamps to the target month's
  length (Jan 31 -> Feb 28/29 -> Mar 31 -> Apr 30). The anchor day is never permanently
  lost to a short month.
* **Overrides re-anchor the schedule permanently.** An override is a ``new_due_date``; from
  its *month* onward the schedule follows the new anchor (new_due_date, +1 month, ...), while
  cycles before it keep the prior anchor. The transition month's due date is *replaced*, not
  duplicated. Multiple overrides in the same month collapse to the last one.
* Actual payments are free-form. Each :class:`Payment` names the cycle it settles, so
  prepayment and back-payment are represented exactly rather than guessed from the date.
* Lateness is day-based: ``days_late = paid - expected``. Drift sums ``max(0, days_late)``,
  so early / prepaid payments contribute 0 and drift can only ever grow.

Uses :class:`datetime.date` (never ``datetime``) so DST and timezones cannot affect the math.
"""

import itertools
from calendar import monthrange
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date

__all__ = [
    "Payment",
    "add_months",
    "cumulative_drift",
    "cycle_number_for_month",
    "days_late",
    "expected_due_date_for_cycle",
    "generate_expected_due_dates",
    "next_expected_date",
]


@dataclass(frozen=True)
class Payment:
    """A single payment settling one billing cycle.

    ``cycle_number`` is the 0-based index from the anchor (cycle 0 == the join/enrollment
    month). A real-world payment that covers several months is modeled as one ``Payment``
    per cycle, all sharing the same ``paid_date``.
    """

    cycle_number: int
    paid_date: date


def add_months(anchor: date, n: int) -> date:
    """Return ``anchor`` shifted by ``n`` calendar months, anchor-day-preserving.

    The day-of-month of the *original* anchor is retained and clamped to the length of the
    target month, so ``Jan 31 + 1 == Feb 28`` (or ``Feb 29`` in a leap year) while
    ``Jan 31 + 2 == Mar 31`` — the 31 is preserved, not drifted to 28.
    """
    # Convert to a 0-based month index to make the year roll-over arithmetic clean.
    month_index = (anchor.year * 12 + (anchor.month - 1)) + n
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    last_day = monthrange(year, month)[1]
    return date(year, month, min(anchor.day, last_day))


def _month_key(d: date) -> tuple[int, int]:
    return (d.year, d.month)


def _normalize_overrides(overrides: Sequence[date]) -> list[date]:
    """Sort override dates by month and collapse multiple in one month to the last given."""
    by_month: dict[tuple[int, int], date] = {}
    for d in sorted(overrides, key=_month_key):
        by_month[_month_key(d)] = d  # later same-month override overwrites -> last wins
    return [by_month[key] for key in sorted(by_month)]


def _iter_due_dates(join_date: date, overrides: Sequence[date]) -> Iterator[date]:
    """Yield the (override-aware) expected due dates in order, indefinitely.

    Walks month by month from the current anchor; when the walk reaches an override's month
    the anchor switches to that override's date (re-anchor) and generation continues from
    there. Comparing at month granularity is what replaces the transition month's due date
    instead of emitting both the old and the new one.
    """
    pending = _normalize_overrides(overrides)
    i = 0
    anchor = join_date
    k = 0
    while True:
        candidate = add_months(anchor, k)
        while i < len(pending) and _month_key(pending[i]) <= _month_key(candidate):
            anchor = pending[i]
            i += 1
            k = 0
            candidate = anchor
        yield candidate
        k += 1


def generate_expected_due_dates(
    join_date: date, up_to: date, overrides: Sequence[date] = ()
) -> list[date]:
    """List every expected due date from the anchor through ``up_to`` (inclusive).

    Returns ``[]`` when ``up_to`` is before the first due date. Honors overrides
    (permanent re-anchor from each override's month).
    """
    return list(
        itertools.takewhile(lambda due: due <= up_to, _iter_due_dates(join_date, overrides))
    )


def expected_due_date_for_cycle(
    join_date: date, cycle_number: int, overrides: Sequence[date] = ()
) -> date:
    """The expected due date for a single cycle (0-based), honoring overrides."""
    return next(itertools.islice(_iter_due_dates(join_date, overrides), cycle_number, None))


def cycle_number_for_month(
    join_date: date, year: int, month: int, overrides: Sequence[date] = ()
) -> int:
    """The cycle index (0-based) whose expected due date falls in ``year``-``month``.

    Override-aware. Raises ``ValueError`` if the month precedes the schedule's first cycle.
    Every month from the join month onward has exactly one cycle.
    """
    target = (year, month)
    due_dates = _iter_due_dates(join_date, overrides)
    idx = 0
    while True:
        due = next(due_dates)
        key = (due.year, due.month)
        if key == target:
            return idx
        if key > target:
            raise ValueError(f"No cycle falls in {year}-{month:02d} (before the schedule starts)")
        idx += 1


def days_late(expected: date, paid: date) -> int:
    """Days between the expected due date and the actual paid date.

    Negative if paid early, zero if on time, positive if late.
    """
    return (paid - expected).days


def cumulative_drift(join_date: date, payments: list[Payment], as_of: date) -> int:
    """Total accrued lateness across every cycle *due on or before* ``as_of``.

    Pure, override-free spec of the drift rule: each payment's expected due date is
    ``add_months(join_date, cycle_number)``. Only cycles whose due date is ``<= as_of`` are
    counted (gating on the due date, not the paid date, is what makes drift monotonically
    non-decreasing as ``as_of`` advances). Each counted cycle contributes
    ``max(0, days_late)``, so early/prepaid payments add 0 and unpaid cycles add nothing.

    The service layer computes a student's drift from the *frozen* ``days_late`` persisted on
    each payment row (which were themselves computed override-aware at record time); this
    function stays the override-free reference exercised by the property tests.
    """
    total = 0
    for payment in payments:
        expected = add_months(join_date, payment.cycle_number)
        if expected <= as_of:
            total += max(0, days_late(expected, payment.paid_date))
    return total


def next_expected_date(join_date: date, as_of: date, overrides: Sequence[date] = ()) -> date:
    """The next scheduled due date on or after ``as_of`` (override-aware).

    Returns the first generated due date ``>= as_of`` (the ">=" convention: a payment due
    today is the next one expected).
    """
    return next(due for due in _iter_due_dates(join_date, overrides) if due >= as_of)
