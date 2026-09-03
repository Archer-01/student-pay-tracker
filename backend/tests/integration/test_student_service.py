"""Integration tests for StudentService."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.services.exceptions import InvalidStudentError, StudentNotFoundError
from app.services.student_service import StudentService


def _enroll(svc: StudentService, name: str = "Amina", **kw: object) -> object:
    defaults: dict[str, object] = {
        "first_name": name,
        "phone": "+212600000000",
        "join_date": date(2023, 3, 5),
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
    assert [s.full_name for s in svc.list(status=StudentStatus.INACTIVE)] == ["Left One"]


def test_update_contact_and_price(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = _enroll(svc)
    svc.update(student.id, phone="+212611111111", custom_price=Decimal("350.00"))
    refreshed = svc.get(student.id)
    assert refreshed.phone == "+212611111111"
    assert refreshed.custom_price == Decimal("350.00")
    assert refreshed.join_date == date(2023, 3, 5)  # anchor untouched


def test_update_leaves_unspecified_fields(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = _enroll(svc, custom_price=Decimal("300.00"))
    svc.update(student.id, custom_price=Decimal("400.00"))
    refreshed = svc.get(student.id)
    assert refreshed.phone == "+212600000000"  # unchanged
    assert refreshed.custom_price == Decimal("400.00")


def test_update_phone_only_leaves_the_price(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = _enroll(svc, custom_price=Decimal("300.00"))
    svc.update(student.id, phone="+212622222222")
    refreshed = svc.get(student.id)
    assert refreshed.phone == "+212622222222"
    assert refreshed.custom_price == Decimal("300.00")  # unchanged


def test_update_cannot_touch_join_date(db_session: Session) -> None:
    # The anchor is immutable at the service layer — the method has no such parameter.
    svc = StudentService(db_session)
    student = _enroll(svc)
    with pytest.raises(TypeError):
        svc.update(student.id, join_date=date(2024, 1, 1))  # type: ignore[call-arg]


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


# --------------------------------------------------------------------------- #
# Name parts and profile fields (sprint 11)
# --------------------------------------------------------------------------- #


def test_full_name_joins_the_parts(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = svc.enroll(first_name="Amina", last_name="Benali", join_date=date(2023, 3, 5))
    assert student.full_name == "Amina Benali"


def test_a_student_may_have_no_surname(db_session: Session) -> None:
    """"Fatima Zahra" is one compound given name — the case a first/last split gets wrong."""
    svc = StudentService(db_session)
    student = svc.enroll(first_name="Fatima Zahra", join_date=date(2023, 3, 5))
    assert student.last_name is None
    assert student.full_name == "Fatima Zahra"


def test_a_blank_surname_is_stored_as_none(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = svc.enroll(first_name="Amina", last_name="   ", join_date=date(2023, 3, 5))
    assert student.last_name is None


def test_names_are_trimmed(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = svc.enroll(first_name="  Amina  ", last_name=" Benali ", join_date=date(2023, 3, 5))
    assert (student.first_name, student.last_name) == ("Amina", "Benali")


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_first_name_is_rejected(db_session: Session, blank: str) -> None:
    with pytest.raises(InvalidStudentError) as exc:
        StudentService(db_session).enroll(first_name=blank, join_date=date(2023, 3, 5))
    assert exc.value.code == "first_name_empty"


def test_update_can_rename(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = svc.enroll(first_name="Amina", last_name="Benali", join_date=date(2023, 3, 5))
    svc.update(student.id, first_name="Amine", last_name="Benali El Fassi")
    assert student.full_name == "Amine Benali El Fassi"


def test_update_rejects_a_blank_first_name(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = svc.enroll(first_name="Amina", join_date=date(2023, 3, 5))
    with pytest.raises(InvalidStudentError):
        svc.update(student.id, first_name="  ")


def test_update_can_clear_the_surname(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = svc.enroll(first_name="Amina", last_name="Benali", join_date=date(2023, 3, 5))
    svc.update(student.id, last_name=None)
    assert student.last_name is None


def test_repeating_defaults_to_false_and_can_be_set(db_session: Session) -> None:
    svc = StudentService(db_session)
    student = svc.enroll(first_name="Amina", join_date=date(2023, 3, 5))
    assert student.is_repeating is False
    svc.update(student.id, is_repeating=True)
    assert student.is_repeating is True


def test_search_matches_either_name_part(db_session: Session) -> None:
    svc = StudentService(db_session)
    svc.enroll(first_name="Amina", last_name="Benali", join_date=date(2023, 3, 5))
    svc.enroll(first_name="Youssef", last_name="El Amrani", join_date=date(2023, 3, 5))
    assert [s.full_name for s in svc.list(query="benali")] == ["Amina Benali"]
    assert [s.full_name for s in svc.list(query="youssef")] == ["Youssef El Amrani"]
    assert [s.full_name for s in svc.list(query="a")] == ["Amina Benali", "Youssef El Amrani"]
    assert svc.list(query="nobody") == []


def test_search_does_not_crash_on_a_student_without_a_surname(db_session: Session) -> None:
    svc = StudentService(db_session)
    svc.enroll(first_name="Fatima Zahra", join_date=date(2023, 3, 5))
    assert [s.full_name for s in svc.list(query="fatima")] == ["Fatima Zahra"]
    assert svc.list(query="zzz") == []


def test_students_are_listed_by_surname(db_session: Session) -> None:
    svc = StudentService(db_session)
    svc.enroll(first_name="Zoe", last_name="Alaoui", join_date=date(2023, 3, 5))
    svc.enroll(first_name="Amina", last_name="Zaki", join_date=date(2023, 3, 5))
    assert [s.full_name for s in svc.list()] == ["Zoe Alaoui", "Amina Zaki"]
