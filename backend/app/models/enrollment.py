"""The ``EnrollmentPeriod`` model — a contiguous span a student was actually attending.

A student's billing schedule is generated from their immutable ``join_date`` forever; periods do
**not** move that anchor. They record when the student was actually present, so that months they
were away can be excluded from what they owe without rewriting their history.

Leaving and returning is therefore append/close-only: closing a period records a departure, and a
return opens a new one. Nothing here re-dates the past.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.student import Student


class EnrollmentPeriod(Base):
    __tablename__ = "enrollment_period"
    __table_args__ = (
        CheckConstraint(
            "leave_date IS NULL OR leave_date >= entry_date",
            name="ck_enrollment_period_dates_ordered",
        ),
        # "At most one open period per student" as a database rule rather than a service promise:
        # a partial unique index over the open rows only. Overlap between *closed* periods can't
        # be expressed this way and is enforced (and tested) in EnrollmentService.
        Index(
            "uq_enrollment_period_one_open",
            "student_id",
            unique=True,
            sqlite_where=text("leave_date IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False
    )
    entry_date: Mapped[date] = mapped_column(nullable=False)
    # NULL means "still attending". Only one such row may exist per student (see the index above).
    leave_date: Mapped[date | None] = mapped_column(nullable=True)
    leave_reason: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    student: Mapped["Student"] = relationship(back_populates="periods")
