"""Student lifecycle: enroll, read, update contact/pricing, change status.

``join_date`` (the drift anchor) is intentionally immutable here — no method accepts it.
"""

from datetime import date
from decimal import Decimal
from typing import Final

from sqlalchemy.orm import Session

from app.models import Student, StudentStatus
from app.repos import ClassRepo, OverrideRepo, PackRepo, PaymentRepo, StudentRepo
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import (
    ClassNotFoundError,
    InvalidPackError,
    InvalidStudentError,
    PackNotFoundError,
    StudentNotFoundError,
)


def _clean_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise InvalidStudentError("first_name_empty")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    """Blank surnames are stored as NULL — "no surname on record", not an empty one."""
    return None if value is None or not value.strip() else value.strip()


class _Unset:
    """Sentinel distinguishing "field omitted" from "field set to None"."""


_UNSET: Final = _Unset()


class StudentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.payments = PaymentRepo(session)
        self.overrides = OverrideRepo(session)
        self.classes = ClassRepo(session)
        self.packs = PackRepo(session)

    def enroll(
        self,
        *,
        first_name: str,
        last_name: str | None = None,
        phone: str | None = None,
        join_date: date,
        status: StudentStatus = StudentStatus.ACTIVE,
        class_id: int | None = None,
        pack_id: int | None = None,
        custom_price: Decimal | None = None,
        price_note: str | None = None,
        is_repeating: bool = False,
    ) -> Student:
        self._require_class(class_id)
        self._require_pack(pack_id)
        self._check_price(custom_price)
        student = Student(
            first_name=_clean_name(first_name),
            last_name=_clean_optional(last_name),
            phone=phone,
            is_repeating=is_repeating,
            join_date=join_date,
            status=status,
            class_id=class_id,
            pack_id=pack_id,
            custom_price=custom_price,
            price_note=price_note,
        )
        self.students.create(student)
        # Every student starts with an open period at their anchor, so "was they attending?" has
        # an answer from day one rather than only after their first leave.
        EnrollmentService(self.session).start(student)
        self.session.commit()
        return student

    def get(self, student_id: int) -> Student:
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)
        return student

    def list(
        self,
        status: StudentStatus | None = None,
        class_id: int | None = None,
        query: str | None = None,
    ) -> list[Student]:
        return self.students.list(status=status, class_id=class_id, query=query)

    def _require_class(self, class_id: int | None) -> None:
        """Reject an unknown class up front, so callers get a domain 404 rather than the
        database's IntegrityError."""
        if class_id is not None and self.classes.get(class_id) is None:
            raise ClassNotFoundError(class_id)

    def _require_pack(self, pack_id: int | None) -> None:
        """Reject an unknown or retired pack up front (a domain error, not an IntegrityError)."""
        if pack_id is None:
            return
        pack = self.packs.get(pack_id)
        if pack is None:
            raise PackNotFoundError(pack_id)
        if not pack.is_active:
            raise InvalidPackError("pack_inactive", pack_id=pack_id)

    @staticmethod
    def _check_price(price: Decimal | None) -> None:
        if price is not None and price < 0:
            raise InvalidPackError("custom_price_negative")

    def delete(self, student_id: int) -> None:
        """Hard-delete a student and cascade to their payments and overrides.

        An admin/dev operation (CLI + API), never exposed in the frontend. Deletion is a
        cascade rather than a refusal: the payment/override FKs are ``ON DELETE RESTRICT``, so
        we remove the child rows explicitly first, keeping this decision in the service layer
        instead of relying on database FK behaviour. This destroys financial/audit history —
        callers are expected to confirm before invoking it.
        """
        student = self.get(student_id)
        for payment in self.payments.list_for_student(student_id):
            self.payments.delete(payment)
        for override in self.overrides.list_for_student(student_id):
            self.overrides.delete(override)
        self.students.delete(student)
        self.session.commit()

    def change_status(self, student_id: int, status: StudentStatus) -> Student:
        student = self.get(student_id)
        student.status = status
        self.session.commit()
        return student

    def update(
        self,
        student_id: int,
        *,
        first_name: str | _Unset = _UNSET,
        last_name: str | None | _Unset = _UNSET,
        phone: str | None | _Unset = _UNSET,
        is_repeating: bool | _Unset = _UNSET,
        status: StudentStatus | _Unset = _UNSET,
        class_id: int | None | _Unset = _UNSET,
        pack_id: int | None | _Unset = _UNSET,
        custom_price: Decimal | None | _Unset = _UNSET,
        price_note: str | None | _Unset = _UNSET,
    ) -> Student:
        """Apply only the provided fields (a single PATCH). ``join_date`` is never accepted.

        Changing ``class_id`` (including to ``None``) is purely organisational: it must not
        affect the anchor, payments, or drift.
        """
        student = self.get(student_id)
        if not isinstance(first_name, _Unset):
            student.first_name = _clean_name(first_name)
        if not isinstance(last_name, _Unset):
            student.last_name = _clean_optional(last_name)
        if not isinstance(phone, _Unset):
            student.phone = phone
        if not isinstance(is_repeating, _Unset):
            student.is_repeating = is_repeating
        if not isinstance(status, _Unset):
            student.status = status
        if not isinstance(class_id, _Unset):
            self._require_class(class_id)
            student.class_id = class_id
        if not isinstance(pack_id, _Unset):
            self._require_pack(pack_id)
            student.pack_id = pack_id
        if not isinstance(custom_price, _Unset):
            # Explicit null clears the arrangement and returns them to the pack price.
            self._check_price(custom_price)
            student.custom_price = custom_price
        if not isinstance(price_note, _Unset):
            student.price_note = price_note
        self.session.commit()
        return student
