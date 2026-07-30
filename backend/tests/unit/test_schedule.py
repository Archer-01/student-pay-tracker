"""Example and edge-case tests for the drift domain core (``app.services.schedule``).

These are the hand-picked scenarios from ``sprint-planning.md`` and the ``drift-invariants``
skill: the canonical acceptance scenario, calendar month-end arithmetic, a DST-adjacent
date (to prove ``date`` math is timezone-agnostic), and the messy real-world payment-timing
cases the user called out (early, prepay, backpay, unpaid, one payment covering two cycles).
"""

from datetime import date

import pytest

from app.services.schedule import (
    Payment,
    add_months,
    cumulative_drift,
    cycle_number_for_month,
    days_late,
    expected_due_date_for_cycle,
    generate_expected_due_dates,
    next_expected_date,
)

# --------------------------------------------------------------------------- #
# add_months — calendar-month arithmetic, anchor-day-preserving + clamped
# --------------------------------------------------------------------------- #


def test_add_months_simple_mid_month() -> None:
    assert add_months(date(2023, 3, 5), 1) == date(2023, 4, 5)
    assert add_months(date(2023, 3, 5), 3) == date(2023, 6, 5)


def test_add_months_zero_returns_anchor() -> None:
    assert add_months(date(2023, 3, 5), 0) == date(2023, 3, 5)


def test_add_months_clamps_jan_31_to_february() -> None:
    # Jan 31 + 1 month is Feb 28 (not Mar 3) in a non-leap year.
    assert add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)


def test_add_months_clamps_jan_31_to_leap_february() -> None:
    # Leap year: Feb 29 exists.
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_add_months_clamps_mar_31_to_apr_30() -> None:
    assert add_months(date(2023, 3, 31), 1) == date(2023, 4, 30)


def test_add_months_preserves_anchor_day_across_short_month() -> None:
    # The anchor day (31) must be *preserved*, not permanently drifted to 28:
    # Jan 31 + 2 months is Mar 31, not Mar 28.
    anchor = date(2023, 1, 31)
    assert add_months(anchor, 1) == date(2023, 2, 28)
    assert add_months(anchor, 2) == date(2023, 3, 31)
    assert add_months(anchor, 3) == date(2023, 4, 30)


def test_add_months_rolls_over_year_boundary() -> None:
    assert add_months(date(2023, 11, 15), 3) == date(2024, 2, 15)
    assert add_months(date(2023, 12, 31), 2) == date(2024, 2, 29)


# --------------------------------------------------------------------------- #
# generate_expected_due_dates
# --------------------------------------------------------------------------- #


def test_generate_includes_join_date_as_first_due_date() -> None:
    join = date(2023, 3, 5)
    dues = generate_expected_due_dates(join, up_to=date(2023, 6, 5))
    assert dues == [
        date(2023, 3, 5),
        date(2023, 4, 5),
        date(2023, 5, 5),
        date(2023, 6, 5),
    ]


def test_generate_up_to_equal_join_returns_single_date() -> None:
    join = date(2023, 3, 5)
    assert generate_expected_due_dates(join, up_to=join) == [join]


def test_generate_up_to_before_join_returns_empty() -> None:
    join = date(2023, 3, 5)
    assert generate_expected_due_dates(join, up_to=date(2023, 3, 4)) == []


def test_generate_stops_before_up_to_when_not_on_a_due_date() -> None:
    join = date(2023, 3, 5)
    # up_to falls between May 5 and Jun 5 -> last included is May 5.
    dues = generate_expected_due_dates(join, up_to=date(2023, 5, 20))
    assert dues == [date(2023, 3, 5), date(2023, 4, 5), date(2023, 5, 5)]


def test_generate_handles_month_end_anchor() -> None:
    join = date(2023, 1, 31)
    dues = generate_expected_due_dates(join, up_to=date(2023, 4, 30))
    assert dues == [
        date(2023, 1, 31),
        date(2023, 2, 28),
        date(2023, 3, 31),
        date(2023, 4, 30),
    ]


# --------------------------------------------------------------------------- #
# days_late
# --------------------------------------------------------------------------- #


def test_days_late_on_time_is_zero() -> None:
    assert days_late(date(2023, 4, 5), date(2023, 4, 5)) == 0


def test_days_late_positive_when_late() -> None:
    assert days_late(date(2023, 4, 5), date(2023, 4, 10)) == 5


def test_days_late_negative_when_early() -> None:
    assert days_late(date(2023, 4, 5), date(2023, 4, 1)) == -4


def test_days_late_is_timezone_agnostic_across_dst_transition() -> None:
    # US spring-forward 2023 was Mar 12. Using ``date`` (not ``datetime``) the
    # gap is exactly the calendar day count regardless of the lost hour.
    assert days_late(date(2023, 3, 11), date(2023, 3, 13)) == 2


# --------------------------------------------------------------------------- #
# cumulative_drift
# --------------------------------------------------------------------------- #


def test_canonical_scenario_drift_is_15() -> None:
    """The acceptance scenario (scoping doc Table 3).

    Join Mar 5; payments each land on the 10th (5 days after the 5th):
    Apr (cycle 1), May (cycle 2), Jun (cycle 3) -> 5 + 5 + 5 = 15.
    """
    join = date(2023, 3, 5)
    payments = [
        Payment(cycle_number=1, paid_date=date(2023, 4, 10)),
        Payment(cycle_number=2, paid_date=date(2023, 5, 10)),
        Payment(cycle_number=3, paid_date=date(2023, 6, 10)),
    ]
    assert cumulative_drift(join, payments, as_of=date(2023, 6, 10)) == 15


def test_drift_zero_for_no_payments() -> None:
    join = date(2023, 3, 5)
    assert cumulative_drift(join, [], as_of=date(2023, 12, 31)) == 0


def test_drift_zero_when_all_on_time() -> None:
    join = date(2023, 3, 5)
    payments = [
        Payment(cycle_number=0, paid_date=date(2023, 3, 5)),
        Payment(cycle_number=1, paid_date=date(2023, 4, 5)),
        Payment(cycle_number=2, paid_date=date(2023, 5, 5)),
    ]
    assert cumulative_drift(join, payments, as_of=date(2023, 5, 5)) == 0


def test_early_payment_contributes_zero_drift() -> None:
    join = date(2023, 3, 5)
    payments = [Payment(cycle_number=1, paid_date=date(2023, 4, 1))]
    assert cumulative_drift(join, payments, as_of=date(2023, 4, 30)) == 0


def test_prepaid_future_cycle_is_excluded_until_its_due_date() -> None:
    # Student prepays cycle 3 (due Jun 5) back on May 1. Gated on the *due* date,
    # so at as_of May 20 the cycle isn't counted yet -> 0.
    join = date(2023, 3, 5)
    payments = [Payment(cycle_number=3, paid_date=date(2023, 5, 1))]
    assert cumulative_drift(join, payments, as_of=date(2023, 5, 20)) == 0
    # Once Jun 5 has passed, it's counted but the early payment is still 0 drift.
    assert cumulative_drift(join, payments, as_of=date(2023, 6, 10)) == 0


def test_backpaid_cycle_contributes_large_drift() -> None:
    # Cycle 1 (due Apr 5) not paid until Jul 3 -> 89 days late.
    join = date(2023, 3, 5)
    payments = [Payment(cycle_number=1, paid_date=date(2023, 7, 3))]
    expected = (date(2023, 7, 3) - date(2023, 4, 5)).days
    assert cumulative_drift(join, payments, as_of=date(2023, 7, 31)) == expected


def test_unpaid_cycle_contributes_zero() -> None:
    # Cycle 1 paid 5 late; cycle 2 (May 5) never paid -> only the 5 counts.
    join = date(2023, 3, 5)
    payments = [Payment(cycle_number=1, paid_date=date(2023, 4, 10))]
    assert cumulative_drift(join, payments, as_of=date(2023, 6, 30)) == 5


def test_single_real_payment_covering_two_cycles() -> None:
    # One real payment on Jun 5 covers Jun (cycle 3, on time) and Jul (cycle 4,
    # prepaid) -> modeled as two rows sharing a paid_date, both 0 drift.
    join = date(2023, 3, 5)
    payments = [
        Payment(cycle_number=3, paid_date=date(2023, 6, 5)),
        Payment(cycle_number=4, paid_date=date(2023, 6, 5)),
    ]
    assert cumulative_drift(join, payments, as_of=date(2023, 8, 1)) == 0


def test_drift_gated_on_due_date_not_paid_date() -> None:
    # A late payment whose *due* date is still in the future is not yet counted.
    join = date(2023, 3, 5)
    payments = [Payment(cycle_number=5, paid_date=date(2023, 3, 20))]
    # cycle 5 is due Aug 5; as_of is before that.
    assert cumulative_drift(join, payments, as_of=date(2023, 7, 1)) == 0


# --------------------------------------------------------------------------- #
# next_expected_date
# --------------------------------------------------------------------------- #


def test_next_expected_mid_cycle_returns_upcoming_due_date() -> None:
    join = date(2023, 3, 5)
    assert next_expected_date(join, as_of=date(2023, 4, 20)) == date(2023, 5, 5)


def test_next_expected_on_a_due_date_returns_that_date() -> None:
    # ">=" convention: a due date that falls on as_of is itself the next expected.
    join = date(2023, 3, 5)
    assert next_expected_date(join, as_of=date(2023, 5, 5)) == date(2023, 5, 5)


def test_next_expected_before_join_returns_join() -> None:
    join = date(2023, 3, 5)
    assert next_expected_date(join, as_of=date(2023, 1, 1)) == join


def test_next_expected_on_join_returns_join() -> None:
    join = date(2023, 3, 5)
    assert next_expected_date(join, as_of=join) == join


def test_next_expected_respects_month_end_anchor() -> None:
    join = date(2023, 1, 31)
    # After Feb 28, the next expected snaps back to the preserved 31 -> Mar 31.
    assert next_expected_date(join, as_of=date(2023, 3, 1)) == date(2023, 3, 31)


# --------------------------------------------------------------------------- #
# Overrides — permanent re-anchor from the override's month forward
# --------------------------------------------------------------------------- #


def test_empty_overrides_matches_sprint1_behavior() -> None:
    join = date(2023, 3, 5)
    up_to = date(2023, 9, 30)
    assert generate_expected_due_dates(join, up_to, ()) == generate_expected_due_dates(join, up_to)
    assert expected_due_date_for_cycle(join, 3) == date(2023, 6, 5)
    assert expected_due_date_for_cycle(join, 3, ()) == add_months(join, 3)


def test_override_permanent_reanchor() -> None:
    # Join Mar 5 (due 5th); override to Jul 20 -> July moves to the 20th, no double charge.
    join = date(2023, 3, 5)
    overrides = [date(2023, 7, 20)]
    assert generate_expected_due_dates(join, date(2023, 9, 30), overrides) == [
        date(2023, 3, 5),
        date(2023, 4, 5),
        date(2023, 5, 5),
        date(2023, 6, 5),
        date(2023, 7, 20),
        date(2023, 8, 20),
        date(2023, 9, 20),
    ]


def test_expected_due_date_for_cycle_with_override() -> None:
    join = date(2023, 3, 5)
    overrides = [date(2023, 7, 20)]
    assert expected_due_date_for_cycle(join, 3, overrides) == date(2023, 6, 5)  # before override
    assert expected_due_date_for_cycle(join, 4, overrides) == date(2023, 7, 20)  # the re-anchor
    assert expected_due_date_for_cycle(join, 6, overrides) == date(2023, 9, 20)  # after


def test_two_overrides_same_month_collapse_last_wins() -> None:
    join = date(2023, 3, 5)
    overrides = [date(2023, 7, 10), date(2023, 7, 25)]
    dues = generate_expected_due_dates(join, date(2023, 8, 31), overrides)
    # Only one July cycle, on the later date; no Jul 10 and no Jul 5.
    assert dues == [
        date(2023, 3, 5),
        date(2023, 4, 5),
        date(2023, 5, 5),
        date(2023, 6, 5),
        date(2023, 7, 25),
        date(2023, 8, 25),
    ]


def test_override_month_end_anchor_clamping() -> None:
    # Jan 31 anchor clamps to Feb 28; a Feb 15 override replaces that month's due date.
    join = date(2023, 1, 31)
    overrides = [date(2023, 2, 15)]
    assert generate_expected_due_dates(join, date(2023, 4, 30), overrides) == [
        date(2023, 1, 31),
        date(2023, 2, 15),
        date(2023, 3, 15),
        date(2023, 4, 15),
    ]


def test_override_day_earlier_than_anchor_stays_increasing() -> None:
    join = date(2023, 3, 5)
    overrides = [date(2023, 7, 2)]  # earlier day than the 5th
    dues = generate_expected_due_dates(join, date(2023, 8, 31), overrides)
    assert dues == [
        date(2023, 3, 5),
        date(2023, 4, 5),
        date(2023, 5, 5),
        date(2023, 6, 5),
        date(2023, 7, 2),
        date(2023, 8, 2),
    ]
    assert all(a < b for a, b in zip(dues, dues[1:], strict=False))


def test_override_in_join_month_reanchors_cycle_zero() -> None:
    join = date(2023, 3, 5)
    overrides = [date(2023, 3, 20)]
    assert generate_expected_due_dates(join, date(2023, 5, 31), overrides) == [
        date(2023, 3, 20),
        date(2023, 4, 20),
        date(2023, 5, 20),
    ]


def test_next_expected_date_with_override() -> None:
    join = date(2023, 3, 5)
    overrides = [date(2023, 7, 20)]
    assert next_expected_date(join, date(2023, 7, 1), overrides) == date(2023, 7, 20)
    assert next_expected_date(join, date(2023, 7, 20), overrides) == date(2023, 7, 20)
    assert next_expected_date(join, date(2023, 8, 1), overrides) == date(2023, 8, 20)


# --------------------------------------------------------------------------- #
# cycle_number_for_month — resolve a calendar month to its cycle index
# --------------------------------------------------------------------------- #


def test_cycle_number_for_month_basic() -> None:
    join = date(2023, 3, 5)
    assert cycle_number_for_month(join, 2023, 3) == 0  # join month
    assert cycle_number_for_month(join, 2023, 4) == 1
    assert cycle_number_for_month(join, 2023, 6) == 3


def test_cycle_number_for_month_crosses_year() -> None:
    join = date(2023, 11, 5)
    assert cycle_number_for_month(join, 2024, 2) == 3


def test_cycle_number_for_month_is_override_aware() -> None:
    join = date(2023, 3, 5)
    overrides = [date(2023, 7, 20)]
    assert cycle_number_for_month(join, 2023, 7, overrides) == 4
    assert cycle_number_for_month(join, 2023, 8, overrides) == 5


def test_cycle_number_for_month_before_schedule_raises() -> None:
    join = date(2023, 3, 5)
    with pytest.raises(ValueError):
        cycle_number_for_month(join, 2023, 2)
