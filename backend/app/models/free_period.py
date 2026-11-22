"""The ``FreePeriod`` model: a stretch of time a student was free on purpose (decision 0014).

A student whose price is 0 on purpose owes nothing; once they are given a price, the months that
fell due while they were free must stay free. Prices are current, not historical (decision 0002),
so that history is kept here, and only that: one row per stretch, opened when the student becomes
free and closed (``to_date``) when they get a price or lose theirs. ``PricingService`` statuses
drive it, through ``services/free_periods.py``; nothing sets these rows by hand.

An unpaid month due on a day in ``[from_date, to_date)`` is not owed. Like an enrolment period,
this only ever removes accrual: drift comes from recorded payments, which no period touches.
"""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class FreePeriod(Base):
    __tablename__ = "free_period"
    __table_args__ = (
        # Strictly after: a stretch of no days is deleted, not kept (a 0 fixed the same day).
        CheckConstraint(
            "to_date IS NULL OR to_date > from_date", name="ck_free_period_dates_ordered"
        ),
        # At most one open stretch per student, as a database rule (like enrolment periods).
        Index(
            "uq_free_period_one_open",
            "student_id",
            unique=True,
            sqlite_where=text("to_date IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_date: Mapped[date] = mapped_column(nullable=False)
    # The day the period was opened, written by the service (``from_date`` can be earlier: an
    # enrolment at 0 is free from the join date). Closed on that same day, it was a mistake.
    opened_on: Mapped[date] = mapped_column(nullable=False)
    # NULL while the student is still free.
    to_date: Mapped[date | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
