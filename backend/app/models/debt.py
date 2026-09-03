"""The ``DebtWriteoff`` model — forgiving what a departed student owed.

Whether a student left owing money is **derived**, not stored: a boolean would go stale the moment
a payment landed. The only thing worth persisting is the teacher's decision to write a debt off,
and that is an audit-log entry in the same style as ``AnchorOverride`` — append-only, with a
mandatory reason, never a mutation.

A write-off is **not a payment**. It must never appear in collected revenue or affect drift; it
exists so that clearing the leavers list doesn't require recording money that was never received.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.student import Student


class DebtWriteoff(Base):
    __tablename__ = "debt_writeoff"
    __table_args__ = (
        CheckConstraint("length(trim(reason)) > 0", name="ck_debt_writeoff_reason_nonempty"),
        CheckConstraint("amount >= 0", name="ck_debt_writeoff_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="CASCADE"), nullable=False
    )
    # A snapshot of what was forgiven, so the record still reads correctly years later even
    # though the derived balance it came from is long gone.
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    reason: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    # A nullable `user_id` belongs here once login lands (BACKLOG §5); adding a nullable column
    # later is a one-line migration, so nothing is stubbed out now.

    student: Mapped["Student"] = relationship(back_populates="writeoffs")
