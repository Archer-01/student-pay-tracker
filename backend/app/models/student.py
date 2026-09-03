"""The ``Student`` model — the anchor of the whole drift domain."""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.anchor_override import AnchorOverride
    from app.models.debt import DebtWriteoff
    from app.models.enrollment import EnrollmentPeriod
    from app.models.pack import Pack
    from app.models.payment import Payment
    from app.models.school_class import SchoolClass


class StudentStatus(enum.StrEnum):
    """Whether a student is currently attending."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class Student(Base):
    __tablename__ = "student"
    __table_args__ = (
        CheckConstraint(
            "custom_price IS NULL OR custom_price >= 0",
            name="ck_student_custom_price_non_negative",
        ),
        CheckConstraint("length(trim(first_name)) > 0", name="ck_student_first_name_nonempty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(nullable=False)
    # Nullable, not empty-string: some students genuinely have no surname on record. "Fatima
    # Zahra" is one compound given name, not a first and last — which is also why the split in
    # migration 0005 is an explicit mapping rather than a split on whitespace.
    last_name: Mapped[str | None] = mapped_column(nullable=True)
    phone: Mapped[str | None] = mapped_column(nullable=True)
    # "Redoublant": repeating the year. Informational — it has no effect on pricing or drift.
    is_repeating: Mapped[bool] = mapped_column(
        nullable=False, default=False, server_default="0"
    )
    # The immutable anchor; the API must never let this move (enforced in Sprint 6).
    join_date: Mapped[date] = mapped_column(nullable=False)
    status: Mapped[StudentStatus] = mapped_column(
        # Store the lowercase values ("active"/"inactive"), not the member names, so the
        # stored form matches the API's ?status=active filter and reads cleanly in exports.
        Enum(StudentStatus, values_callable=lambda e: [m.value for m in e], name="studentstatus"),
        nullable=False,
        default=StudentStatus.ACTIVE,
    )
    # Organisational only — a class never affects drift, the anchor, or pricing. Nullable
    # because a student can exist before being placed in a group; ON DELETE SET NULL is a
    # database-level backstop only, since ClassService refuses to delete a non-empty class.
    class_id: Mapped[int | None] = mapped_column(
        ForeignKey("school_class.id", ondelete="SET NULL"), nullable=True
    )
    # What they pay: the pack's price, unless `custom_price` overrides it. Nullable because a
    # student can exist before being put on a pack; such a student is simply not billed.
    pack_id: Mapped[int | None] = mapped_column(
        ForeignKey("pack.id", ondelete="RESTRICT"), nullable=True
    )
    # Set only when this student does not pay the pack price. `price_note` says why, and the two
    # are shown together so an arrangement is visible rather than buried.
    custom_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    price_note: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    @property
    def full_name(self) -> str:
        """Display name. String assembly, not domain logic — it exists so the PDF exports, the
        filename slug and the CLI all render a name the same way, in one place."""
        return f"{self.first_name} {self.last_name}".strip() if self.last_name else self.first_name

    payments: Mapped[list["Payment"]] = relationship(back_populates="student")
    # passive_deletes=True: the FK is ON DELETE CASCADE, so the database removes a student's
    # periods. Without this SQLAlchemy tries to null out `student_id` first, which the NOT NULL
    # constraint rejects. (Payments and overrides are ON DELETE RESTRICT and are removed
    # explicitly by StudentService.delete instead.)
    periods: Mapped[list["EnrollmentPeriod"]] = relationship(
        back_populates="student", passive_deletes=True
    )
    writeoffs: Mapped[list["DebtWriteoff"]] = relationship(
        back_populates="student", passive_deletes=True
    )
    overrides: Mapped[list["AnchorOverride"]] = relationship(back_populates="student")
    school_class: Mapped["SchoolClass | None"] = relationship(back_populates="students")
    pack: Mapped["Pack | None"] = relationship(back_populates="students")
