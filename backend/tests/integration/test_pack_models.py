"""Model + repo tests for packs and subjects, and a student's link to their pack.

Constraint tests assert each rule lives in the *schema* (and therefore the migration), not just
in Python — every violation must raise ``IntegrityError`` on flush.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ClassLevel, Pack, Student, Subject
from app.repos import PackRepo, StudentRepo


def _pack(session: Session, **overrides: object) -> Pack:
    defaults: dict[str, object] = {
        "name": "Maths seul",
        "level": ClassLevel.BAC2,
        "price": Decimal("120.00"),
    }
    defaults.update(overrides)
    pack = Pack(**defaults)
    session.add(pack)
    session.flush()
    return pack


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
# pack
# --------------------------------------------------------------------------- #


def test_pack_level_is_stored_as_its_value(db_session: Session) -> None:
    """Shares ClassLevel with school_class, and stores "2BAC" rather than "BAC2"."""
    _pack(db_session)
    stored = db_session.execute(text("SELECT level FROM pack")).scalar_one()
    assert stored == "2BAC"


def test_pack_name_and_level_are_unique_together(db_session: Session) -> None:
    _pack(db_session, name="Maths seul", level=ClassLevel.BAC2)
    with pytest.raises(IntegrityError):
        _pack(db_session, name="Maths seul", level=ClassLevel.BAC2)


def test_same_offering_at_a_different_level_is_a_separate_pack(db_session: Session) -> None:
    """The whole point of putting `level` on the pack: one price per (offering, level)."""
    _pack(db_session, name="Maths seul", level=ClassLevel.BAC2, price=Decimal("150"))
    _pack(db_session, name="Maths seul", level=ClassLevel.AC1, price=Decimal("100"))


def test_pack_price_must_be_non_negative(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        _pack(db_session, price=Decimal("-1"))


def test_pack_name_must_not_be_blank(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        _pack(db_session, name="  ")


def test_pack_is_active_defaults_to_true(db_session: Session) -> None:
    assert _pack(db_session).is_active is True


# --------------------------------------------------------------------------- #
# subject / pack_subject
# --------------------------------------------------------------------------- #


def test_subject_name_is_unique(db_session: Session) -> None:
    db_session.add(Subject(name="Maths"))
    db_session.flush()
    db_session.add(Subject(name="Maths"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_pack_carries_its_subjects_both_ways(db_session: Session) -> None:
    maths, physics = Subject(name="Maths"), Subject(name="Physique")
    pack = _pack(db_session)
    pack.subjects = [maths, physics]
    db_session.flush()
    db_session.refresh(pack)
    assert sorted(s.name for s in pack.subjects) == ["Maths", "Physique"]
    assert [p.id for p in maths.packs] == [pack.id]


# --------------------------------------------------------------------------- #
# a student's pack
# --------------------------------------------------------------------------- #


def test_student_pack_is_optional(db_session: Session) -> None:
    student = _student(db_session)
    assert student.pack_id is None
    assert student.pack is None
    assert student.custom_price is None


def test_student_belongs_to_a_pack_both_ways(db_session: Session) -> None:
    pack = _pack(db_session)
    student = _student(db_session, pack_id=pack.id)
    db_session.refresh(pack)
    assert student.pack is pack
    assert [s.id for s in pack.students] == [student.id]


def test_student_pack_id_must_reference_a_real_pack(db_session: Session) -> None:
    with pytest.raises(IntegrityError):
        _student(db_session, pack_id=999)


def test_custom_price_must_be_non_negative(db_session: Session) -> None:
    pack = _pack(db_session)
    with pytest.raises(IntegrityError):
        _student(db_session, pack_id=pack.id, custom_price=Decimal("-1"))


def test_a_pack_in_use_cannot_be_deleted_at_the_database_level(db_session: Session) -> None:
    """ON DELETE RESTRICT backs up the service rule, so a stray delete can't orphan a student."""
    pack = _pack(db_session)
    _student(db_session, pack_id=pack.id)
    db_session.delete(pack)
    with pytest.raises(IntegrityError):
        db_session.flush()


# --------------------------------------------------------------------------- #
# repos
# --------------------------------------------------------------------------- #


def test_pack_repo_find_by_name_and_level(db_session: Session) -> None:
    _pack(db_session, name="Maths seul", level=ClassLevel.BAC2)
    repo = PackRepo(db_session)
    assert repo.find("Maths seul", ClassLevel.BAC2) is not None
    assert repo.find("Maths seul", ClassLevel.AC1) is None


def test_pack_repo_list_filters(db_session: Session) -> None:
    _pack(db_session, name="A", level=ClassLevel.AC1)
    _pack(db_session, name="B", level=ClassLevel.BAC2, is_active=False)
    repo = PackRepo(db_session)
    assert len(repo.list()) == 2
    assert [p.name for p in repo.list(level=ClassLevel.AC1)] == ["A"]
    assert [p.name for p in repo.list(active=True)] == ["A"]


def test_pack_repo_list_by_name_spans_levels(db_session: Session) -> None:
    _pack(db_session, name="Maths seul", level=ClassLevel.AC1)
    _pack(db_session, name="Maths seul", level=ClassLevel.BAC2)
    _pack(db_session, name="Pack complet", level=ClassLevel.AC1)
    assert len(PackRepo(db_session).list_by_name("Maths seul")) == 2


def test_student_repo_counts_students_on_a_pack(db_session: Session) -> None:
    pack = _pack(db_session)
    _student(db_session, pack_id=pack.id)
    _student(db_session, first_name="Other")
    assert StudentRepo(db_session).count_on_pack(pack.id) == 1
