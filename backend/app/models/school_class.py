"""The ``SchoolClass`` model — a level + name grouping of students.

Named ``SchoolClass`` (table ``school_class``) because ``class`` is a Python keyword and a
reserved word in SQL. A class is *organisational only*: it groups students for rosters and
exports and never influences drift, the anchor, or pricing.

``ClassLevel`` is deliberately declared here and re-exported from ``app.models`` because it is
shared: the pack model (backlog sprint 10) scopes its prices by the same levels, and a second
definition would let the two drift apart.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.student import Student


class ClassLevel(enum.StrEnum):
    """Moroccan school levels, declared in school order.

    Order matters and is load-bearing: it is the ordering used for display, because sorting the
    *values* alphabetically is wrong ("1BAC" would land before "2AC"). Members can't start with
    a digit, so the member name and the stored value differ — the value is what's stored, filtered
    on, and exported (the ``StudentStatus`` precedent).
    """

    AC1 = "1AC"
    AC2 = "2AC"
    AC3 = "3AC"
    TC = "TC"
    BAC1 = "1BAC"
    BAC2 = "2BAC"


class SchoolClass(Base):
    __tablename__ = "school_class"
    __table_args__ = (
        UniqueConstraint("level", "name", name="uq_school_class_level_name"),
        CheckConstraint("length(trim(name)) > 0", name="ck_school_class_name_nonempty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[ClassLevel] = mapped_column(
        # Store the values ("2BAC"), not the member names ("BAC2"), so the stored form matches
        # the API's ?level=2BAC filter and reads cleanly in exports.
        Enum(ClassLevel, values_callable=lambda e: [m.value for m in e], name="classlevel"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    students: Mapped[list["Student"]] = relationship(back_populates="school_class")
