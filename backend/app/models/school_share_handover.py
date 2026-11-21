"""The ``SchoolShareHandover`` model: the school's share of a month, handed over.

The share itself is derived, never stored (see ``services/school_share.py``): a flat percentage
of what came in that month. What is worth persisting is the teacher's record that he gave it to
the school, and how much he gave, so a payment recorded later for that month shows up as a
shortfall instead of silently moving a figure already settled.

A handover is cash given to the school. It is never revenue, never a payment, and never touches
drift.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SchoolShareHandover(Base):
    __tablename__ = "school_share_handover"
    __table_args__ = (
        UniqueConstraint("year", "month", name="uq_school_share_handover_month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="ck_school_share_handover_month"),
        CheckConstraint("amount >= 0", name="ck_school_share_handover_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(nullable=False)
    month: Mapped[int] = mapped_column(nullable=False)
    # What was handed over, as the share stood when it was marked.
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    handed_on: Mapped[date] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
