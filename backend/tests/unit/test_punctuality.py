"""How late a student usually pays: the average lateness of their last six payments.

It reads the frozen ``days_late`` on payments and changes nothing else, so drift is untouched.
"""

from datetime import date
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from app.services.ledger_service import LedgerEntry
from app.services.punctuality import RECENT_PAYMENTS, average_days_late

AS_OF = date(2026, 11, 14)


def paid(month: int, days_late: int, year: int = 2026) -> LedgerEntry:
    due = date(year, month, 5)
    return LedgerEntry(
        cycle_number=month,
        expected_due_date=due,
        paid_date=due,
        days_late=days_late,
        amount=Decimal("200"),
        cumulative_drift=0,
    )


def unpaid(month: int) -> LedgerEntry:
    return LedgerEntry(
        cycle_number=month,
        expected_due_date=date(2026, month, 5),
        paid_date=None,
        days_late=None,
        amount=None,
        cumulative_drift=0,
    )


def test_no_payment_yet_means_nothing_to_say() -> None:
    assert average_days_late([], AS_OF) is None
    assert average_days_late([unpaid(10), unpaid(11)], AS_OF) is None


def test_always_on_time_is_zero() -> None:
    assert average_days_late([paid(9, 0), paid(10, 0), paid(11, 0)], AS_OF) == 0


def test_the_average_rounds_half_up() -> None:
    assert average_days_late([paid(9, 2), paid(10, 3)], AS_OF) == 3  # 2.5
    assert average_days_late([paid(9, 1), paid(10, 1), paid(11, 2)], AS_OF) == 1  # 1.33


def test_paying_early_counts_as_on_time_not_as_credit() -> None:
    # Ten days early doesn't make up for ten days late another month.
    assert average_days_late([paid(9, -10), paid(10, 10)], AS_OF) == 5


def test_only_the_last_six_payments_count() -> None:
    # A bad first year, then a year of paying on time: it's how they pay now that matters.
    old = [paid(m, 20, year=2025) for m in range(1, 13)]
    recent = [paid(m, 0) for m in range(5, 11)]
    assert average_days_late(old + recent, AS_OF) == 0
    assert RECENT_PAYMENTS == 6


def test_unpaid_months_and_payments_made_in_advance_are_left_out() -> None:
    advance = LedgerEntry(
        cycle_number=12,
        expected_due_date=date(2026, 12, 5),
        paid_date=date(2026, 11, 10),
        days_late=0,
        amount=Decimal("200"),
        cumulative_drift=0,
    )
    assert average_days_late([paid(9, 8), unpaid(10), paid(11, 8), advance], AS_OF) == 8


@given(st.lists(st.integers(min_value=-30, max_value=90), min_size=1, max_size=24))
def test_the_average_sits_between_the_best_and_worst_counted_payment(lateness: list[int]) -> None:
    entries = [
        LedgerEntry(
            cycle_number=i,
            expected_due_date=date(2024 + i // 12, i % 12 + 1, 5),
            paid_date=date(2024 + i // 12, i % 12 + 1, 5),
            days_late=d,
            amount=Decimal("200"),
            cumulative_drift=0,
        )
        for i, d in enumerate(lateness)
    ]
    counted = [max(0, d) for d in lateness[-RECENT_PAYMENTS:]]
    result = average_days_late(entries, AS_OF)
    assert result is not None
    assert min(counted) <= result <= max(counted)
