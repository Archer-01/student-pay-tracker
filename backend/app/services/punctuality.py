"""How late a student usually pays: the average lateness of their recent payments.

A reading of the frozen ``days_late`` already on each payment; nothing here feeds drift or
changes a payment. Recent payments only, so a student who used to be late and has since
settled into paying on time is shown as they are now.
"""

from collections.abc import Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the ledger summary uses this module, so only the type crosses back
    from app.services.ledger_service import LedgerEntry

# How many of the latest payments the average looks at.
RECENT_PAYMENTS = 6


def average_days_late(entries: Sequence["LedgerEntry"], as_of: date) -> int | None:
    """Average days late over the last ``RECENT_PAYMENTS`` payments due by ``as_of``.

    Rounded half up to whole days. Paying early counts as on time (0), never as credit against
    a late month. A month paid in advance isn't counted until it falls due, and a student with
    no payment due yet gets ``None``: there is nothing to say about them.
    """
    paid = sorted(
        (e for e in entries if e.paid_date is not None and e.expected_due_date <= as_of),
        key=lambda e: e.expected_due_date,
    )[-RECENT_PAYMENTS:]
    if not paid:
        return None
    total = sum(max(0, e.days_late or 0) for e in paid)
    return int((Decimal(total) / len(paid)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
