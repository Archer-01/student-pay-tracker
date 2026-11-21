"""What a student pays — one number, resolved in one place.

    effective price = ``student.custom_price`` if set, else the price of ``student.pack``

A student with no pack and no custom price has no price, and so is not billed: they show as owing
nothing, exactly as a zero fee did before. That is a legal, visible state (the UI nudges to assign
a pack), not an error.

**Prices are not historical.** Changing a pack's price changes what its students owe for months
they haven't paid yet, and moving a student to another pack reprices their unpaid past months too.
This is a deliberate simplification: recorded payments keep their own frozen ``amount``, so money
already taken is never rewritten — only the outstanding estimate moves.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Student
from app.repos import StudentRepo


class PricingService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)

    def price_of(self, student: Student) -> Decimal:
        """The monthly price for ``student``: their agreed price, else their pack's, else zero."""
        if student.custom_price is not None:
            return student.custom_price
        if student.pack is not None:
            return student.pack.price
        return Decimal("0")

    def amount_for_cycles(self, student: Student, due_dates: list[date]) -> Decimal:
        """Total owed for the given unpaid cycles.

        Takes the dates rather than a count so the signature survives if pricing ever becomes
        date-dependent again; today every cycle is priced the same.
        """
        return self.price_of(student) * len(due_dates)

    def billable(self, student: Student) -> bool:
        """Whether a cycle costs anything — an unpriced or free month is not arrears."""
        return self.price_of(student) > 0
