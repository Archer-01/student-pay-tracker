"""The school's share of the money a teacher receives, and what is left for the teacher.

The teacher pays the school owner a flat percentage of every payment received (25% today, set by
``SCHOOL_SHARE_PERCENT``). This splits money *received*, so it follows paid dates exactly as
"collected" does; a write-off is not money received and never enters it.

Rounding is done once per month: the school's part of a month is rounded half-up to the cent,
the teacher's part is whatever is left (so the two always add up to what came in), and a year's
share is the sum of its months, so the year always equals the months it is made of.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class ShareSplit:
    percent: Decimal
    school: Decimal
    teacher: Decimal


def split(collected: Decimal, percent: Decimal) -> ShareSplit:
    """Split one month's (or one total's) collected money at ``percent``."""
    school = (collected * percent / Decimal(100)).quantize(_CENT, rounding=ROUND_HALF_UP)
    return ShareSplit(percent=percent, school=school, teacher=collected - school)


def split_months(collected: list[Decimal], percent: Decimal) -> tuple[list[ShareSplit], ShareSplit]:
    """Split each month on its own, and total them: the year's share is the sum of the months'."""
    months = [split(amount, percent) for amount in collected]
    school = sum((m.school for m in months), Decimal("0"))
    total = sum(collected, Decimal("0"))
    return months, ShareSplit(percent=percent, school=school, teacher=total - school)
