"""Handing the school its share: which months are due, and the record that one was handed over.

The share of a month is derived, as in the reports: ``school_share.split`` of what came in that
month, by paid date. A handover records what the teacher actually gave and when, so a payment
recorded later for an already settled month shows up as what is still missing ("short") rather
than silently changing a figure he has already acted on. Marking the month again replaces the
record with the full share.

A handover is cash given to the school: never revenue, never a payment, never drift. Services
take the percentage as a parameter; only the API reads the setting.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy.orm import Session

from app.models import SchoolShareHandover
from app.repos import PaymentRepo, SchoolShareHandoverRepo
from app.services.exceptions import HandoverNotFoundError, InvalidHandoverError
from app.services.schedule import add_months
from app.services.school_share import split

# running: the month isn't over; nothing: nothing came in; due: not handed over yet;
# handed: handed over in full; short: handed over, but a later payment raised the share.
ShareStatus = Literal["running", "nothing", "due", "handed", "short"]


@dataclass(frozen=True)
class ShareMonth:
    year: int
    month: int
    collected: Decimal
    # The school's part of what came in, as it stands now.
    due: Decimal
    handed_amount: Decimal | None
    handed_on: date | None
    status: ShareStatus
    # What is still to hand over: all of it when due, the difference when short, else 0.
    remaining: Decimal


ShareMonths = list[ShareMonth]


class SchoolShareHandoverService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.payments = PaymentRepo(session)
        self.handovers = SchoolShareHandoverRepo(session)

    def months(self, today: date, share_percent: Decimal) -> ShareMonths:
        """Every month from the first payment's to today's, newest first; none at a 0% share."""
        first = self.payments.earliest_paid_date()
        if share_percent <= 0 or first is None:
            return []
        handed = {(h.year, h.month): h for h in self.handovers.all()}
        months: ShareMonths = []
        start, last = first.replace(day=1), today.replace(day=1)
        while start <= last:
            handover = handed.get((start.year, start.month))
            months.append(self._month(start, today, share_percent, handover))
            start = add_months(start, 1)
        return months[::-1]

    def pending(self, today: date, share_percent: Decimal) -> ShareMonth | None:
        """Last month's share, while any of it is still to hand over."""
        last_month = add_months(today.replace(day=1), -1)
        for month in self.months(today, share_percent):
            if (month.year, month.month) == (last_month.year, last_month.month):
                return month if month.remaining > 0 else None
        return None

    def mark(
        self, year: int, month: int, *, handed_on: date, share_percent: Decimal, today: date
    ) -> SchoolShareHandover:
        """Record that ``month``'s share was handed over on ``handed_on``: the share as it stands
        now. Marking a month again replaces its record."""
        if share_percent <= 0:
            raise InvalidHandoverError("school_share_off")
        if (year, month) >= (today.year, today.month):
            raise InvalidHandoverError("share_month_not_over", year=year, month=month)
        if handed_on > today:
            raise InvalidHandoverError("handover_in_future")
        due = split(self._collected(date(year, month, 1)), share_percent).school
        if due <= 0:
            raise InvalidHandoverError("nothing_to_hand_over", year=year, month=month)

        handover = self.handovers.get(year, month)
        if handover is None:
            handover = self.handovers.create(
                SchoolShareHandover(year=year, month=month, amount=due, handed_on=handed_on)
            )
        else:
            handover.amount = due
            handover.handed_on = handed_on
        self.session.commit()
        return handover

    def unmark(self, year: int, month: int) -> None:
        handover = self.handovers.get(year, month)
        if handover is None:
            raise HandoverNotFoundError(year, month)
        self.handovers.delete(handover)
        self.session.commit()

    # -- internals --------------------------------------------------------- #

    def _collected(self, month_start: date) -> Decimal:
        payments = self.payments.list_paid_between(month_start, add_months(month_start, 1))
        return sum((p.amount for p in payments), Decimal("0"))

    def _month(
        self,
        month_start: date,
        today: date,
        share_percent: Decimal,
        handover: SchoolShareHandover | None,
    ) -> ShareMonth:
        collected = self._collected(month_start)
        due = split(collected, share_percent).school
        status: ShareStatus
        remaining = Decimal("0")
        if month_start == today.replace(day=1):
            status = "running"
        elif handover is not None and handover.amount >= due:
            status = "handed"
        elif handover is not None:
            status, remaining = "short", due - handover.amount
        elif due > 0:
            status, remaining = "due", due
        else:
            status = "nothing"
        return ShareMonth(
            year=month_start.year,
            month=month_start.month,
            collected=collected,
            due=due,
            handed_amount=handover.amount if handover else None,
            handed_on=handover.handed_on if handover else None,
            status=status,
            remaining=remaining,
        )
