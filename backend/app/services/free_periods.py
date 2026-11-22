"""Keeping a student's free periods in step with their price (decision 0014).

One rule, called after anything that can change a price (a student edited, enrolled, or their
pack repriced): if the student is free now and no period is open, open one; if they aren't and
one is open, close it. State, not events, so calling it twice changes nothing.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import FreePeriod, Student
from app.repos import FreePeriodRepo
from app.services.pricing_service import PricingService


class FreePeriodService:
    def __init__(self, session: Session) -> None:
        self.periods = FreePeriodRepo(session)
        self.pricing = PricingService(session)

    def follow_price(self, student: Student, today: date, *, free_from: date | None = None) -> None:
        """Open or close the student's free period to match their price as it now stands.

        ``free_from`` is when a period that opens starts (``today`` unless given: an enrolment
        at 0 is free from the join date). A period closed on the day it was opened was a mistake
        corrected at once, so it is removed rather than closed, whatever ``from_date`` says: a 0
        typed by mistake, even at a backdated enrolment, leaves nothing. So is one that would
        cover no day (closed on or before its ``from_date``).
        """
        free = self.pricing.price_status(student) == "free"
        current = self.periods.open_for(student.id)
        if free and current is None:
            self.periods.create(
                FreePeriod(student_id=student.id, from_date=free_from or today, opened_on=today)
            )
        elif not free and current is not None:
            if today <= current.opened_on or today <= current.from_date:
                self.periods.delete(current)
            else:
                current.to_date = today

    @staticmethod
    def covers(periods: list[FreePeriod], day: date) -> bool:
        """Whether ``day`` falls in one of ``periods`` (``from_date`` in, ``to_date`` out)."""
        return any(p.from_date <= day and (p.to_date is None or day < p.to_date) for p in periods)
