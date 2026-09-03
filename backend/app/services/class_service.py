"""Classes: create, rename, list in school order, delete, and build a roster.

A class is **organisational only**. Nothing here may touch a student's ``join_date``, payments,
or drift — moving a student between classes, or removing them from one entirely, must leave every
number in the drift domain untouched. That is pinned by tests rather than left to convention.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final

from sqlalchemy.orm import Session

from app.models import ClassLevel, SchoolClass, Student
from app.repos import ClassRepo, StudentRepo
from app.services.exceptions import (
    ClassNotEmptyError,
    ClassNotFoundError,
    DuplicateClassError,
    InvalidClassError,
)
from app.services.ledger_service import LedgerService
from app.services.pricing_service import PricingService

# Declaration order in ClassLevel is school order; sorting on the stored value would put "1BAC"
# before "2AC". Materialised once so ordering is a dict lookup, not a linear scan per row.
LEVEL_ORDER: Final[dict[ClassLevel, int]] = {
    level: index for index, level in enumerate(ClassLevel)
}


class _Unset:
    """Sentinel distinguishing "field omitted" from "field set to None"."""


_UNSET: Final = _Unset()


@dataclass(frozen=True)
class RosterRow:
    """One student in a class, with the two figures the teacher actually reads."""

    student: Student
    cumulative_drift: int
    months_overdue: int
    amount_owed: Decimal
    monthly_price: Decimal


# ClassService has a method named `list` (matching StudentService), which shadows the builtin for
# any annotation declared after it. Aliasing here, at module scope, keeps `roster`'s return type
# correct for mypy as well as at runtime, whatever order the methods end up in.
RosterRows = list[RosterRow]


def _clean_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise InvalidClassError("class_name_empty")
    return cleaned


class ClassService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.classes = ClassRepo(session)
        self.students = StudentRepo(session)

    def create(self, *, level: ClassLevel, name: str) -> SchoolClass:
        cleaned = _clean_name(name)
        self._require_free(level, cleaned)
        school_class = self.classes.create(SchoolClass(level=level, name=cleaned))
        self.session.commit()
        return school_class

    def get_or_create(self, *, level: ClassLevel, name: str) -> SchoolClass:
        """Return the class with this natural key, creating it if absent.

        Idempotent counterpart to :meth:`create`, for callers that want the class to exist
        rather than to assert it doesn't (the dev seed re-runs against a populated database).
        """
        cleaned = _clean_name(name)
        existing = self.classes.find(level, cleaned)
        if existing is not None:
            return existing
        return self.create(level=level, name=cleaned)

    def get(self, class_id: int) -> SchoolClass:
        school_class = self.classes.get(class_id)
        if school_class is None:
            raise ClassNotFoundError(class_id)
        return school_class

    def list(self, *, level: ClassLevel | None = None) -> list[SchoolClass]:
        """Classes in school order (1AC → 2BAC), then by name."""
        classes = self.classes.list(level=level)
        return sorted(classes, key=lambda c: (LEVEL_ORDER[c.level], c.name))

    def student_count(self, class_id: int) -> int:
        return self.students.count_in_class(class_id)

    def update(
        self,
        class_id: int,
        *,
        level: ClassLevel | _Unset = _UNSET,
        name: str | _Unset = _UNSET,
    ) -> SchoolClass:
        """Apply only the provided fields (a single PATCH)."""
        school_class = self.get(class_id)
        new_level = school_class.level if isinstance(level, _Unset) else level
        new_name = school_class.name if isinstance(name, _Unset) else _clean_name(name)
        if (new_level, new_name) != (school_class.level, school_class.name):
            self._require_free(new_level, new_name)
        school_class.level = new_level
        school_class.name = new_name
        self.session.commit()
        return school_class

    def delete(self, class_id: int) -> None:
        """Delete an empty class. A class with students is refused, never silently emptied."""
        school_class = self.get(class_id)
        count = self.student_count(class_id)
        if count:
            raise ClassNotEmptyError(class_id, count)
        self.classes.delete(school_class)
        self.session.commit()

    def roster(self, class_id: int, as_of: date) -> RosterRows:
        """The class's students with their drift and arrears as of ``as_of``."""
        self.get(class_id)  # 404 for an unknown class, rather than an empty roster
        ledger = LedgerService(self.session)
        pricing = PricingService(self.session)
        rows: RosterRows = []
        for student in self.students.list(class_id=class_id):
            # Reuse the ledger's summary rather than recomputing drift/arrears here — the
            # "an unpriced student owes nothing" rule must live in exactly one place.
            summary = ledger.student_summary(student.id, as_of)
            rows.append(
                RosterRow(
                    student=student,
                    cumulative_drift=summary.cumulative_drift,
                    months_overdue=summary.months_overdue,
                    amount_owed=summary.amount_owed,
                    monthly_price=pricing.price_of(student),
                )
            )
        return rows

    def _require_free(self, level: ClassLevel, name: str) -> None:
        if self.classes.find(level, name) is not None:
            raise DuplicateClassError(level.value, name)
