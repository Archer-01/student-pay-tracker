"""Integration tests for StudentService."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.services.exceptions import StudentNotFoundError
from app.services.student_service import StudentService


def _enroll(svc: StudentService, name: str = "Amina", **kw: object) -> object:
    defaults: dict[str, object] = {
        "name": name,
        "phone": "+212600000000",
        "join_date": date(2023, 3, 5),
        "fee": Decimal("300.00"),
    }
    defaults.update(kw)
    return svc.enroll(**defaults)  # type: ignore[arg-type]


def test_enroll_persists_and_defaults_to_active(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = _enroll(svc)
    assert student.id is not None
    assert svc.get(student.id).status is StudentStatus.ACTIVE


def test_get_missing_raises(db_session: Session) -> None:
    with pytest.raises(StudentNotFoundError):
        StudentService(db_session).get(999)


def test_list_and_status_filter(db_session: Session) -> None:
    svc = StudentService(db_session)
    _enroll(svc, name="Active One")
    _enroll(svc, name="Left One", status=StudentStatus.INACTIVE)
    assert len(svc.list()) == 2
    assert [s.name for s in svc.list(status=StudentStatus.INACTIVE)] == ["Left One"]


def test_update_contact_fee(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = _enroll(svc)
    svc.update_contact_fee(student.id, phone="+212611111111", fee=Decimal("350.00"))
    refreshed = svc.get(student.id)
    assert refreshed.phone == "+212611111111"
    assert refreshed.fee == Decimal("350.00")
    assert refreshed.join_date == date(2023, 3, 5)  # anchor untouched


def test_update_contact_fee_leaves_unspecified_fields(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = _enroll(svc, fee=Decimal("300.00"))
    svc.update_contact_fee(student.id, fee=Decimal("400.00"))
    refreshed = svc.get(student.id)
    assert refreshed.phone == "+212600000000"  # unchanged
    assert refreshed.fee == Decimal("400.00")


def test_update_phone_only_leaves_fee(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = _enroll(svc, fee=Decimal("300.00"))
    svc.update_contact_fee(student.id, phone="+212622222222")
    refreshed = svc.get(student.id)
    assert refreshed.phone == "+212622222222"
    assert refreshed.fee == Decimal("300.00")  # unchanged


def test_update_cannot_touch_join_date(db_session: Session) -> None:
    # The anchor is immutable at the service layer — the method has no such parameter.
    svc = StudentService(db_session)
    student = _enroll(svc)
    with pytest.raises(TypeError):
        svc.update_contact_fee(student.id, join_date=date(2024, 1, 1))  # type: ignore[call-arg]


def test_change_status(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = _enroll(svc)
    svc.change_status(student.id, StudentStatus.INACTIVE)
    assert svc.get(student.id).status is StudentStatus.INACTIVE


def test_delete_removes_student(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = _enroll(svc)
    svc.delete(student.id)
    with pytest.raises(StudentNotFoundError):
        svc.get(student.id)


def test_delete_missing_raises(db_session: Session) -> None:
    with pytest.raises(StudentNotFoundError):
        StudentService(db_session).delete(999)


def test_delete_cascades_to_payments_and_overrides(db_session: Session) -> None:
    # The payment/override FKs are ON DELETE RESTRICT; deletion must still succeed by
    # removing the child rows first, not error out on the constraint.
    from datetime import date

    from app.repos import OverrideRepo, PaymentRepo
    from app.services.override_service import OverrideService
    from app.services.payment_service import PaymentService

    svc = StudentService(db_session)
    student = _enroll(svc)
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=Decimal("300")
    )
    OverrideService(db_session).create_override(
        student_id=student.id, new_due_date=date(2023, 7, 20), reason="agreed shift"
    )

    svc.delete(student.id)

    assert PaymentRepo(db_session).list_for_student(student.id) == []
    assert OverrideRepo(db_session).list_for_student(student.id) == []
