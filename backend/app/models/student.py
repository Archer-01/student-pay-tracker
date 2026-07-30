"""The ``Student`` model — the anchor of the whole drift domain."""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.anchor_override import AnchorOverride
    from app.models.payment import Payment


class StudentStatus(enum.StrEnum):
    """Whether a student is currently attending."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class Student(Base):
    __tablename__ = "student"
    __table_args__ = (CheckConstraint("fee >= 0", name="ck_student_fee_non_negative"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    phone: Mapped[str | None] = mapped_column(nullable=True)
    # The immutable anchor; the API must never let this move (enforced in Sprint 6).
    join_date: Mapped[date] = mapped_column(nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[StudentStatus] = mapped_column(
        # Store the lowercase values ("active"/"inactive"), not the member names, so the
        # stored form matches the API's ?status=active filter and reads cleanly in exports.
        Enum(StudentStatus, values_callable=lambda e: [m.value for m in e], name="studentstatus"),
        nullable=False,
        default=StudentStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    payments: Mapped[list["Payment"]] = relationship(back_populates="student")
    overrides: Mapped[list["AnchorOverride"]] = relationship(back_populates="student")
