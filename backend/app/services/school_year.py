"""A student's months laid out as the school year the teacher thinks in, September to August.

The student PDF draws these twelve tiles instead of a long table of rows that all look alike.
The rules are the app's (``frontend/src/lib/schoolYear.ts``), so paper and screen agree.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from app.services.ledger_service import LedgerEntry

# paid: on time or early (months paid in advance included); late: paid, but late; due: owed;
# away: not paid because the student was away, so not owed; upcoming: not due yet;
# none: nothing expected, before joining or after leaving.
TileState = Literal["paid", "late", "due", "away", "upcoming", "none"]


@dataclass(frozen=True)
class MonthTile:
    month: date  # the first of the month
    state: TileState
    entry: LedgerEntry | None = None


def school_year_start(day: date) -> int:
    """The school year a date falls in, named by the year its September is in."""
    return day.year if day.month >= 9 else day.year - 1


def _months_of(start_year: int) -> list[date]:
    return [
        date(start_year if month >= 9 else start_year + 1, month, 1)
        for month in (9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8)
    ]


def month_tiles(
    entries: Sequence[LedgerEntry],
    start_year: int,
    *,
    join_date: date,
    today: date,
    enrolled: bool,
) -> list[MonthTile]:
    """Twelve tiles, September to August.

    The ledger already holds every month that has come due (and any paid in advance); a month
    without an entry is either not due yet or not expected at all. ``enrolled`` decides which:
    someone who has left is expected to pay nothing further.
    """
    by_month = {e.expected_due_date.replace(day=1): e for e in entries}
    join_month = join_date.replace(day=1)
    this_month = today.replace(day=1)
    tiles: list[MonthTile] = []
    for month in _months_of(start_year):
        entry = by_month.get(month)
        if entry is not None:
            if entry.paid_date is not None:
                late = (entry.days_late or 0) > 0
                tiles.append(MonthTile(month, "late" if late else "paid", entry))
            else:
                tiles.append(MonthTile(month, "away" if entry.suspended else "due", entry))
        elif month >= join_month and month >= this_month and enrolled:
            # No entry and not in the past: this month's day hasn't come, or it's a later month.
            tiles.append(MonthTile(month, "upcoming"))
        else:
            tiles.append(MonthTile(month, "none"))
    return tiles


def school_years(entries: Sequence[LedgerEntry], join_date: date, today: date) -> list[int]:
    """The school years worth showing: from the one the student joined in to the current one,
    or further if they have paid that far ahead."""
    first = school_year_start(join_date)
    last = max(
        [school_year_start(today), *(school_year_start(e.expected_due_date) for e in entries)]
    )
    return list(range(first, max(first, last) + 1))
