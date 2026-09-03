"""Packs — what a student is enrolled in, and what it costs.

A **pack** is a named, level-scoped set of subjects with a price: *Maths seul · 2BAC · 150 DH*.
There is deliberately no separate "enrollment type" concept — "Maths only", "Maths + Physics" and
the full four-subject pack are all just packs, so adding an offering is a row rather than a code
change. Prices vary by level, so each (name, level) pair is its own row.

``pack.price`` is the price. A student who has agreed something different carries a
``custom_price`` on their own row (with a ``price_note`` saying why) — there is exactly one number
per student, and no second pricing concept.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Column,
    Enum,
    ForeignKey,
    Numeric,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.school_class import ClassLevel

if TYPE_CHECKING:
    from app.models.student import Student

# Association table: packs <-> subjects. Plain Table (no model) — it carries no data of its own.
# Subjects are RESTRICTed so a subject in use can't vanish; the link rows die with their pack.
pack_subject = Table(
    "pack_subject",
    Base.metadata,
    Column("pack_id", ForeignKey("pack.id", ondelete="CASCADE"), primary_key=True),
    Column("subject_id", ForeignKey("subject.id", ondelete="RESTRICT"), primary_key=True),
)


class Subject(Base):
    """A taught subject (Maths, Physique, …). Its own table so a name is spelled one way."""

    __tablename__ = "subject"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="ck_subject_name_nonempty"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False, unique=True)

    packs: Mapped[list["Pack"]] = relationship(secondary=pack_subject, back_populates="subjects")


class Pack(Base):
    __tablename__ = "pack"
    __table_args__ = (
        UniqueConstraint("name", "level", name="uq_pack_name_level"),
        CheckConstraint("price >= 0", name="ck_pack_price_non_negative"),
        CheckConstraint("length(trim(name)) > 0", name="ck_pack_name_nonempty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # The offering, e.g. "Maths seul". Shared across this offering's level-variants.
    name: Mapped[str] = mapped_column(nullable=False)
    level: Mapped[ClassLevel] = mapped_column(
        Enum(ClassLevel, values_callable=lambda e: [m.value for m in e], name="classlevel"),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # Retired packs are hidden from the assignment dropdown but still render on historical rows.
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    subjects: Mapped[list[Subject]] = relationship(
        secondary=pack_subject, back_populates="packs", order_by=Subject.name
    )
    # passive_deletes="all" stops SQLAlchemy nulling `student.pack_id` ahead of a parent delete,
    # which would silently unassign students and defeat the ON DELETE RESTRICT. With it, deleting
    # a pack that students are on raises, so the database backs up PackService's 409 rather than
    # being bypassed by any code that deletes through the ORM.
    students: Mapped[list["Student"]] = relationship(
        back_populates="pack", passive_deletes="all"
    )
