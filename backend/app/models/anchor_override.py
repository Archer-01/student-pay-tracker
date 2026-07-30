"""The ``AnchorOverride`` model — an audit-log entry, never a mutation.

Overrides record an agreed change to a student's due date going forward. They must never touch
``student.join_date`` or existing payment rows (that rule is enforced in the Sprint 3 service);
here the model is just an append-only log with a mandatory, non-empty reason.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.student import Student


class AnchorOverride(Base):
    __tablename__ = "anchor_override"
    __table_args__ = (
        CheckConstraint("length(trim(reason)) > 0", name="ck_anchor_override_reason_nonempty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("student.id", ondelete="RESTRICT"), nullable=False
    )
    new_due_date: Mapped[date] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    student: Mapped["Student"] = relationship(back_populates="overrides")
