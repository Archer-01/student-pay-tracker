"""The ``Payment`` model — one row per settled billing cycle.

``expected_due_date`` and ``days_late`` are *persisted* values written by the service layer
(Sprint 3) at insert time. They are never computed here: keeping all date arithmetic out of
the model is a Sprint 2 exit criterion.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.student import Student


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (
        UniqueConstraint("student_id", "cycle_number", name="uq_payment_student_cycle"),
        CheckConstraint("amount >= 0", name="ck_payment_amount_non_negative"),
        CheckConstraint("cycle_number >= 0", name="ck_payment_cycle_number_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="RESTRICT"), nullable=False
    )
    cycle_number: Mapped[int] = mapped_column(nullable=False)
    paid_date: Mapped[date] = mapped_column(nullable=False)
    expected_due_date: Mapped[date] = mapped_column(nullable=False)
    days_late: Mapped[int] = mapped_column(nullable=False)  # may be negative (early)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    student: Mapped["Student"] = relationship(back_populates="payments")
