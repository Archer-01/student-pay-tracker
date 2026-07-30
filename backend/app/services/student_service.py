"""Student lifecycle: enroll, read, update contact/fee, change status.

``join_date`` (the drift anchor) is intentionally immutable here — no method accepts it.
"""

from datetime import date
from decimal import Decimal
from typing import Final

from sqlalchemy.orm import Session

from app.models import Student, StudentStatus
from app.repos import StudentRepo
from app.services.exceptions import StudentNotFoundError


class _Unset:
    """Sentinel distinguishing "field omitted" from "field set to None"."""


_UNSET: Final = _Unset()


class StudentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)

    def enroll(
        self,
        *,
        name: str,
        phone: str | None,
        join_date: date,
        fee: Decimal,
        status: StudentStatus = StudentStatus.ACTIVE,
    ) -> Student:
        student = Student(name=name, phone=phone, join_date=join_date, fee=fee, status=status)
        self.students.create(student)
        self.session.commit()
        return student

    def get(self, student_id: int) -> Student:
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)
        return student

    def list(self, status: StudentStatus | None = None) -> list[Student]:
        return self.students.list(status=status)

    def update_contact_fee(
        self, student_id: int, *, phone: str | None = None, fee: Decimal | None = None
    ) -> Student:
        """Update contact and/or fee. ``None`` means "leave unchanged"."""
        student = self.get(student_id)
        if phone is not None:
            student.phone = phone
        if fee is not None:
            student.fee = fee
        self.session.commit()
        return student

    def change_status(self, student_id: int, status: StudentStatus) -> Student:
        student = self.get(student_id)
        student.status = status
        self.session.commit()
        return student

    def update(
        self,
        student_id: int,
        *,
        phone: str | None | _Unset = _UNSET,
        fee: Decimal | _Unset = _UNSET,
        status: StudentStatus | _Unset = _UNSET,
    ) -> Student:
        """Apply only the provided fields (a single PATCH). ``join_date`` is never accepted."""
        student = self.get(student_id)
        if not isinstance(phone, _Unset):
            student.phone = phone
        if not isinstance(fee, _Unset):
            student.fee = fee
        if not isinstance(status, _Unset):
            student.status = status
        self.session.commit()
        return student
