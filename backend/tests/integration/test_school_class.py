"""Model + repo tests for ``SchoolClass`` and a student's class membership.

Constraint tests assert the rule lives in the *schema* (and therefore the migration), not just
in Python — each violation must raise ``IntegrityError`` on flush.
"""

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ClassLevel, SchoolClass, Student
from app.repos import ClassRepo, StudentRepo


def _class(session: Session, **overrides: object) -> SchoolClass:
    defaults: dict[str, object] = {"level": ClassLevel.BAC2, "name": "Groupe A"}
    defaults.update(overrides)
    school_class = SchoolClass(**defaults)
    session.add(school_class)
    session.flush()
    return school_class


def _student(session: Session, **overrides: object) -> Student:
    defaults: dict[str, object] = {
        "first_name": "Amina",
        "phone": None,
        "join_date": date(2023, 3, 5),
    }
    defaults.update(overrides)
    student = Student(**defaults)
    session.add(student)
    session.flush()
    return student


# --------------------------------------------------------------------------- #
# Levels
# --------------------------------------------------------------------------- #


def test_levels_are_declared_in_school_order() -> None:
    """Declaration order is the ordering used for display — alphabetical sorting is wrong here
    ("1BAC" would sort before "2AC"), so the enum's own order is the single source of truth."""
    assert [level.value for level in ClassLevel] == ["1AC", "2AC", "3AC", "TC", "1BAC", "2BAC"]


def test_level_is_stored_as_its_value_not_its_member_name(db_session: Session) -> None:
    """Matches the ``StudentStatus`` precedent: the stored form is what the API filter and the
    exports use, so it must be "2BAC", not "BAC2"."""
    _class(db_session)
    stored = db_session.execute(text("SELECT level FROM school_class")).scalar_one()
    assert stored == "2BAC"


# --------------------------------------------------------------------------- #
# Constraints
# --------------------------------------------------------------------------- #


def test_level_and_name_are_unique_together(db_session: Session) -> None:
    _class(db_session, level=ClassLevel.BAC2, name="Groupe A")
    with pytest.raises(IntegrityError):
        _class(db_session, level=ClassLevel.BAC2, name="Groupe A")


def test_same_name_allowed_at_a_different_level(db_session: Session) -> None:
    _class(db_session, level=ClassLevel.BAC2, name="Groupe A")
    _class(db_session, level=ClassLevel.AC1, name="Groupe A")  # must not raise


def test_name_must_not_be_blank(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        _class(db_session, name="   ")


# --------------------------------------------------------------------------- #
# Membership
# --------------------------------------------------------------------------- #


def test_student_class_is_optional(db_session: Session) -> None:
    student = _student(db_session)
    assert student.class_id is None
    assert student.school_class is None


def test_student_belongs_to_a_class_both_ways(db_session: Session) -> None:
    school_class = _class(db_session)
    student = _student(db_session, class_id=school_class.id)
    db_session.refresh(school_class)
    assert student.school_class is school_class
    assert [s.id for s in school_class.students] == [student.id]


def test_student_class_id_must_reference_a_real_class(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        _student(db_session, class_id=999)


# --------------------------------------------------------------------------- #
# ClassRepo — thin CRUD, no business logic
# --------------------------------------------------------------------------- #


def test_repo_create_and_get(db_session: Session) -> None:
    repo = ClassRepo(db_session)
    created = repo.create(SchoolClass(level=ClassLevel.AC1, name="Groupe A"))
    assert created.id is not None
    assert repo.get(created.id) is created


def test_repo_get_missing_returns_none(db_session: Session) -> None:
    assert ClassRepo(db_session).get(999) is None


def test_repo_list_filters_by_level(db_session: Session) -> None:
    _class(db_session, level=ClassLevel.AC1, name="A")
    _class(db_session, level=ClassLevel.BAC2, name="B")
    repo = ClassRepo(db_session)
    assert [c.name for c in repo.list(level=ClassLevel.AC1)] == ["A"]
    assert len(repo.list()) == 2


def test_repo_find_by_level_and_name(db_session: Session) -> None:
    _class(db_session, level=ClassLevel.AC1, name="Groupe A")
    repo = ClassRepo(db_session)
    assert repo.find(ClassLevel.AC1, "Groupe A") is not None
    assert repo.find(ClassLevel.BAC2, "Groupe A") is None


def test_repo_delete(db_session: Session) -> None:
    repo = ClassRepo(db_session)
    created = repo.create(SchoolClass(level=ClassLevel.AC1, name="A"))
    repo.delete(created)
    assert repo.get(created.id) is None


def test_repo_list_students_of_a_class(db_session: Session) -> None:
    school_class = _class(db_session)
    _student(db_session, first_name="In", class_id=school_class.id)
    _student(db_session, first_name="Out")
    assert [s.full_name for s in StudentRepo(db_session).list(class_id=school_class.id)] == ["In"]
