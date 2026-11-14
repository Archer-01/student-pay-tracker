"""The school year as twelve month tiles, September to August: the student PDF draws these.

The same rules as the app's `frontend/src/lib/schoolYear.ts`, case for case, so the paper and
the screen never disagree about a month.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.ledger_service import LedgerEntry
from app.services.school_year import TileState, month_tiles, school_year_start, school_years


def entry(cycle: int, due: date, *, suspended: bool = False) -> LedgerEntry:
    return LedgerEntry(
        cycle_number=cycle,
        expected_due_date=due,
        paid_date=None,
        days_late=None,
        amount=None,
        cumulative_drift=0,
        suspended=suspended,
    )


def paid(cycle: int, due: date, paid_on: date, days_late: int = 0) -> LedgerEntry:
    return LedgerEntry(
        cycle_number=cycle,
        expected_due_date=due,
        paid_date=paid_on,
        days_late=days_late,
        amount=Decimal("200"),
        cumulative_drift=0,
    )


JOINED = date(2026, 9, 5)
TODAY = date(2026, 11, 14)


def states(entries: list[LedgerEntry], **over: object) -> list[TileState]:
    args: dict[str, object] = {"join_date": JOINED, "today": TODAY, "enrolled": True} | over
    return [tile.state for tile in month_tiles(entries, 2026, **args)]  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("day", "year"),
    [(date(2026, 9, 1), 2026), (date(2026, 12, 31), 2026), (date(2027, 1, 15), 2026),
     (date(2027, 8, 31), 2026)],
)
def test_a_date_belongs_to_the_school_year_its_september_starts(day: date, year: int) -> None:
    assert school_year_start(day) == year


def test_the_tiles_run_september_to_august() -> None:
    tiles = month_tiles([], 2026, join_date=JOINED, today=TODAY, enrolled=True)
    assert [(t.month.year, t.month.month) for t in tiles] == [
        (2026, 9), (2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2),
        (2027, 3), (2027, 4), (2027, 5), (2027, 6), (2027, 7), (2027, 8),
    ]


def test_paid_paid_late_owed_and_not_yet_due_are_told_apart() -> None:
    entries = [
        paid(0, date(2026, 9, 5), date(2026, 9, 5)),
        paid(1, date(2026, 10, 5), date(2026, 10, 13), 8),
        entry(2, date(2026, 11, 5)),
    ]
    assert states(entries)[:4] == ["paid", "late", "due", "upcoming"]


def test_a_tile_keeps_its_entry_for_the_details() -> None:
    late = paid(1, date(2026, 10, 5), date(2026, 10, 13), 8)
    tiles = month_tiles([late], 2026, join_date=JOINED, today=TODAY, enrolled=True)
    assert tiles[1].entry is late
    assert tiles[0].entry is None


def test_a_month_paid_in_advance_is_paid() -> None:
    entries = [
        paid(0, date(2026, 9, 5), date(2026, 9, 5)),
        paid(3, date(2026, 12, 5), date(2026, 11, 3)),
    ]
    assert states(entries)[3] == "paid"


def test_a_month_the_student_was_away_is_not_owed() -> None:
    entries = [
        paid(0, date(2026, 9, 5), date(2026, 9, 5)),
        entry(1, date(2026, 10, 5), suspended=True),
    ]
    assert states(entries)[1] == "away"


def test_months_before_joining_are_blank() -> None:
    assert states([], join_date=date(2026, 11, 2))[:3] == ["none", "none", "upcoming"]


def test_this_month_is_not_due_until_its_day_comes() -> None:
    # Joined on the 26th: on the 14th of the next month, that month's payment isn't due yet.
    entries = [paid(0, date(2026, 10, 26), date(2026, 11, 3), 8)]
    assert states(entries, join_date=date(2026, 10, 26))[2] == "upcoming"


def test_nothing_more_is_expected_from_a_student_who_left() -> None:
    entries = [paid(0, date(2026, 9, 5), date(2026, 9, 5))]
    assert states(entries, enrolled=False)[3] == "none"


def test_the_years_run_from_joining_to_now() -> None:
    assert school_years([], date(2025, 3, 10), TODAY) == [2024, 2025, 2026]


def test_the_years_reach_as_far_as_a_payment_made_in_advance() -> None:
    entries = [paid(12, date(2027, 9, 5), TODAY)]
    assert school_years(entries, JOINED, TODAY) == [2026, 2027]
