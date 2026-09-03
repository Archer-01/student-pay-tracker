"""ClassService — the domain rules around classes.

A class is organisational only: creating, renaming, moving students in and out, and deleting
must never touch drift, the anchor, or payments. Several tests below exist purely to pin that.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import ClassLevel
from app.services.class_service import ClassService
from app.services.exceptions import (
    ClassNotEmptyError,
    ClassNotFoundError,
    DuplicateClassError,
    InvalidClassError,
)
from app.services.ledger_service import LedgerService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

_FEE = Decimal("300")


def _student(session: Session, name: str = "Amina", **kw: object) -> object:
    return StudentService(session).enroll(
        first_name=name, phone=None, join_date=date(2023, 3, 5), custom_price=_FEE, **kw
    )


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #


def test_create_returns_a_persisted_class(db_session: Session) -> None:
    created = ClassService(db_session).create(level=ClassLevel.BAC2, name="Groupe A")
    assert created.id is not None
    assert created.level is ClassLevel.BAC2
    assert created.name == "Groupe A"


def test_create_strips_surrounding_whitespace(db_session: Session) -> None:
    created = ClassService(db_session).create(level=ClassLevel.BAC2, name="  Groupe A  ")
    assert created.name == "Groupe A"


@pytest.mark.parametrize("name", ["", "   ", "\t\n"])
def test_create_rejects_a_blank_name(db_session: Session, name: str) -> None:
    with pytest.raises(InvalidClassError) as exc:
        ClassService(db_session).create(level=ClassLevel.BAC2, name=name)
    assert exc.value.code == "class_name_empty"


def test_update_rejects_a_blank_name(db_session: Session) -> None:
    service = ClassService(db_session)
    created = service.create(level=ClassLevel.AC1, name="A")
    with pytest.raises(InvalidClassError):
        service.update(created.id, name="  ")


def test_create_rejects_a_duplicate_level_and_name(db_session: Session) -> None:
    service = ClassService(db_session)
    service.create(level=ClassLevel.BAC2, name="Groupe A")
    with pytest.raises(DuplicateClassError):
        service.create(level=ClassLevel.BAC2, name="Groupe A")


def test_duplicate_check_ignores_surrounding_whitespace(db_session: Session) -> None:
    service = ClassService(db_session)
    service.create(level=ClassLevel.BAC2, name="Groupe A")
    with pytest.raises(DuplicateClassError):
        service.create(level=ClassLevel.BAC2, name="  Groupe A ")


def test_same_name_at_a_different_level_is_allowed(db_session: Session) -> None:
    service = ClassService(db_session)
    service.create(level=ClassLevel.BAC2, name="Groupe A")
    service.create(level=ClassLevel.AC1, name="Groupe A")  # must not raise


def test_get_or_create_creates_when_absent(db_session: Session) -> None:
    created = ClassService(db_session).get_or_create(level=ClassLevel.AC1, name="A")
    assert created.id is not None


def test_get_or_create_returns_the_existing_class(db_session: Session) -> None:
    service = ClassService(db_session)
    first = service.create(level=ClassLevel.AC1, name="A")
    assert service.get_or_create(level=ClassLevel.AC1, name="  A ").id == first.id


def test_get_or_create_rejects_a_blank_name(db_session: Session) -> None:
    with pytest.raises(InvalidClassError):
        ClassService(db_session).get_or_create(level=ClassLevel.AC1, name=" ")


# --------------------------------------------------------------------------- #
# get / list
# --------------------------------------------------------------------------- #


def test_get_unknown_class_raises(db_session: Session) -> None:
    with pytest.raises(ClassNotFoundError) as exc:
        ClassService(db_session).get(999)
    assert exc.value.code == "class_not_found"


def test_list_is_ordered_by_school_level_then_name(db_session: Session) -> None:
    """Not alphabetical by value — "1BAC" must come after "3AC", not before "2AC"."""
    service = ClassService(db_session)
    service.create(level=ClassLevel.BAC2, name="B")
    service.create(level=ClassLevel.AC2, name="B")
    service.create(level=ClassLevel.AC2, name="A")
    service.create(level=ClassLevel.BAC1, name="A")
    service.create(level=ClassLevel.TC, name="A")
    assert [(c.level.value, c.name) for c in service.list()] == [
        ("2AC", "A"),
        ("2AC", "B"),
        ("TC", "A"),
        ("1BAC", "A"),
        ("2BAC", "B"),
    ]


def test_list_filters_by_level(db_session: Session) -> None:
    service = ClassService(db_session)
    service.create(level=ClassLevel.AC1, name="A")
    service.create(level=ClassLevel.BAC2, name="B")
    assert [c.name for c in service.list(level=ClassLevel.AC1)] == ["A"]


def test_student_count(db_session: Session) -> None:
    service = ClassService(db_session)
    created = service.create(level=ClassLevel.AC1, name="A")
    _student(db_session, "In", class_id=created.id)
    _student(db_session, "Out")
    assert service.student_count(created.id) == 1


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #


def test_update_renames(db_session: Session) -> None:
    service = ClassService(db_session)
    created = service.create(level=ClassLevel.AC1, name="A")
    assert service.update(created.id, name="Groupe A").name == "Groupe A"


def test_update_can_change_level(db_session: Session) -> None:
    service = ClassService(db_session)
    created = service.create(level=ClassLevel.AC1, name="A")
    assert service.update(created.id, level=ClassLevel.BAC2).level is ClassLevel.BAC2


def test_update_rejects_a_collision(db_session: Session) -> None:
    service = ClassService(db_session)
    service.create(level=ClassLevel.AC1, name="A")
    second = service.create(level=ClassLevel.AC1, name="B")
    with pytest.raises(DuplicateClassError):
        service.update(second.id, name="A")


def test_update_to_its_own_name_is_not_a_collision(db_session: Session) -> None:
    service = ClassService(db_session)
    created = service.create(level=ClassLevel.AC1, name="A")
    assert service.update(created.id, name="A").name == "A"


def test_update_unknown_class_raises(db_session: Session) -> None:
    with pytest.raises(ClassNotFoundError):
        ClassService(db_session).update(999, name="A")


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #


def test_delete_an_empty_class(db_session: Session) -> None:
    service = ClassService(db_session)
    created = service.create(level=ClassLevel.AC1, name="A")
    service.delete(created.id)
    with pytest.raises(ClassNotFoundError):
        service.get(created.id)


def test_delete_refuses_a_class_with_students(db_session: Session) -> None:
    service = ClassService(db_session)
    created = service.create(level=ClassLevel.AC1, name="A")
    _student(db_session, class_id=created.id)
    with pytest.raises(ClassNotEmptyError) as exc:
        service.delete(created.id)
    assert exc.value.code == "class_not_empty"
    assert service.get(created.id) is not None  # not deleted


def test_delete_unknown_class_raises(db_session: Session) -> None:
    with pytest.raises(ClassNotFoundError):
        ClassService(db_session).delete(999)


# --------------------------------------------------------------------------- #
# roster
# --------------------------------------------------------------------------- #


def test_roster_lists_members_with_drift_and_arrears(db_session: Session) -> None:
    service = ClassService(db_session)
    created = service.create(level=ClassLevel.AC1, name="A")
    student = _student(db_session, "Amina", class_id=created.id)
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=_FEE
    )  # due Apr 5 -> 5 days late
    _student(db_session, "Outsider")

    rows = service.roster(created.id, as_of=date(2023, 4, 30))
    assert [r.student.full_name for r in rows] == ["Amina"]
    assert rows[0].cumulative_drift == 5
    assert rows[0].months_overdue == 1  # cycle 0 (Mar 5) unpaid


def test_roster_of_an_empty_class_is_empty(db_session: Session) -> None:
    service = ClassService(db_session)
    created = service.create(level=ClassLevel.AC1, name="A")
    assert service.roster(created.id, as_of=date(2023, 4, 30)) == []


def test_roster_unknown_class_raises(db_session: Session) -> None:
    with pytest.raises(ClassNotFoundError):
        ClassService(db_session).roster(999, as_of=date(2023, 4, 30))


# --------------------------------------------------------------------------- #
# Classes are organisational only — the drift domain must not notice them.
# --------------------------------------------------------------------------- #


def test_moving_between_classes_does_not_change_drift(db_session: Session) -> None:
    service = ClassService(db_session)
    first = service.create(level=ClassLevel.AC1, name="A")
    second = service.create(level=ClassLevel.BAC2, name="B")
    student = _student(db_session, class_id=first.id)
    payments = PaymentService(db_session)
    payments.record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=_FEE
    )
    as_of = date(2023, 6, 30)
    ledger = LedgerService(db_session)
    before = ledger.cumulative_drift(student.id, as_of)
    before_ledger = ledger.get_ledger(student.id, as_of)

    StudentService(db_session).update(student.id, class_id=second.id)

    assert ledger.cumulative_drift(student.id, as_of) == before
    assert ledger.get_ledger(student.id, as_of) == before_ledger


def test_unassigning_a_student_does_not_change_drift(db_session: Session) -> None:
    service = ClassService(db_session)
    created = service.create(level=ClassLevel.AC1, name="A")
    student = _student(db_session, class_id=created.id)
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=_FEE
    )
    as_of = date(2023, 6, 30)
    before = LedgerService(db_session).cumulative_drift(student.id, as_of)
    StudentService(db_session).update(student.id, class_id=None)
    assert student.class_id is None
    assert LedgerService(db_session).cumulative_drift(student.id, as_of) == before


def test_enrolling_into_an_unknown_class_raises(db_session: Session) -> None:
    with pytest.raises(ClassNotFoundError):
        _student(db_session, class_id=999)


def test_updating_to_an_unknown_class_raises(db_session: Session) -> None:
    student = _student(db_session)
    with pytest.raises(ClassNotFoundError):
        StudentService(db_session).update(student.id, class_id=999)
