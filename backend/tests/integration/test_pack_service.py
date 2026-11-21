"""PackService — the price list, and the rules that keep an offering's variants coherent.

Because `level` lives on the pack, an offering like "Maths seul" is physically several rows. The
service is what stops them drifting apart: name and subject edits apply to every variant at once.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import ClassLevel, Pack
from app.services.exceptions import (
    DuplicatePackError,
    InvalidPackError,
    PackInUseError,
    PackNotFoundError,
)
from app.services.pack_service import PackService
from app.services.student_service import StudentService

_JOIN = date(2023, 3, 5)
_GRID = {ClassLevel.AC1: Decimal("100"), ClassLevel.BAC2: Decimal("150")}


def _offering(service: PackService, name: str) -> list[Pack]:
    """One pack per level of `_GRID`, sharing a name and a subject: an offering, as the CLI
    edits it with `update_offering`."""
    return [
        service.create(name=name, level=lv, price=p, subjects=["Maths"]) for lv, p in _GRID.items()
    ]


def _student(session: Session, name: str = "Amina", **kw: object):
    return StudentService(session).enroll(first_name=name, phone=None, join_date=_JOIN, **kw)


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #


def test_create_a_pack(db_session: Session) -> None:
    pack = PackService(db_session).create(
        name="  Maths seul ", level=ClassLevel.BAC2, price=Decimal("150"), subjects=["Maths"]
    )
    assert pack.name == "Maths seul"
    assert [s.name for s in pack.subjects] == ["Maths"]


def test_create_requires_at_least_one_subject(db_session: Session) -> None:
    with pytest.raises(InvalidPackError) as exc:
        PackService(db_session).create(
            name="X", level=ClassLevel.BAC2, price=Decimal("1"), subjects=[]
        )
    assert exc.value.code == "pack_no_subjects"


def test_create_rejects_a_blank_name(db_session: Session) -> None:
    with pytest.raises(InvalidPackError) as exc:
        PackService(db_session).create(
            name="  ", level=ClassLevel.BAC2, price=Decimal("1"), subjects=["Maths"]
        )
    assert exc.value.code == "pack_name_empty"


def test_create_rejects_a_negative_price(db_session: Session) -> None:
    with pytest.raises(InvalidPackError) as exc:
        PackService(db_session).create(
            name="X", level=ClassLevel.BAC2, price=Decimal("-1"), subjects=["Maths"]
        )
    assert exc.value.code == "pack_price_negative"


def test_create_rejects_a_duplicate_name_and_level(db_session: Session) -> None:
    service = PackService(db_session)
    service.create(name="X", level=ClassLevel.BAC2, price=Decimal("1"), subjects=["Maths"])
    with pytest.raises(DuplicatePackError):
        service.create(name="X", level=ClassLevel.BAC2, price=Decimal("2"), subjects=["Maths"])


def test_subjects_are_shared_not_duplicated(db_session: Session) -> None:
    """ "Maths" is one row however many packs include it."""
    service = PackService(db_session)
    first = service.create(
        name="A", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths", "Physique"]
    )
    second = service.create(name="B", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"])
    maths_ids = {s.id for s in first.subjects if s.name == "Maths"}
    assert maths_ids == {s.id for s in second.subjects if s.name == "Maths"}


def test_duplicate_subject_names_collapse(db_session: Session) -> None:
    pack = PackService(db_session).create(
        name="A", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths", " Maths ", ""]
    )
    assert [s.name for s in pack.subjects] == ["Maths"]


# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# update_offering — variants must never diverge
# --------------------------------------------------------------------------- #


def test_editing_subjects_applies_to_every_level_variant(db_session: Session) -> None:
    service = PackService(db_session)
    _offering(service, "Maths seul")
    service.update_offering("Maths seul", subjects=["Maths", "Physique"])
    variants = service.list()
    assert len(variants) == 2
    for variant in variants:
        assert sorted(s.name for s in variant.subjects) == ["Maths", "Physique"]


def test_renaming_an_offering_renames_every_variant(db_session: Session) -> None:
    service = PackService(db_session)
    _offering(service, "Maths seul")
    service.update_offering("Maths seul", new_name="Maths uniquement")
    assert {p.name for p in service.list()} == {"Maths uniquement"}


def test_renaming_onto_an_existing_offering_is_rejected(db_session: Session) -> None:
    service = PackService(db_session)
    _offering(service, "A")
    _offering(service, "B")
    with pytest.raises(DuplicatePackError):
        service.update_offering("B", new_name="A")


def test_updating_an_unknown_offering_raises(db_session: Session) -> None:
    with pytest.raises(InvalidPackError) as exc:
        PackService(db_session).update_offering("nope", subjects=["Maths"])
    assert exc.value.code == "pack_offering_unknown"


# --------------------------------------------------------------------------- #
# update / reprice
# --------------------------------------------------------------------------- #


def test_update_changes_one_cell_only(db_session: Session) -> None:
    service = PackService(db_session)
    packs = _offering(service, "Maths seul")
    target = next(p for p in packs if p.level is ClassLevel.AC1)
    service.update(target.id, price=Decimal("111"))
    prices = {p.level: p.price for p in service.list()}
    assert prices[ClassLevel.AC1] == Decimal("111")
    assert prices[ClassLevel.BAC2] == Decimal("150")


def test_update_can_deactivate(db_session: Session) -> None:
    service = PackService(db_session)
    pack = service.create(name="X", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"])
    assert service.update(pack.id, is_active=False).is_active is False
    assert service.list(active=True) == []


def test_update_unknown_pack_raises(db_session: Session) -> None:
    with pytest.raises(PackNotFoundError):
        PackService(db_session).update(999, price=Decimal("1"))


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #


def test_delete_an_unused_pack(db_session: Session) -> None:
    service = PackService(db_session)
    pack = service.create(name="X", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"])
    service.delete(pack.id)
    with pytest.raises(PackNotFoundError):
        service.get(pack.id)


def test_delete_refuses_a_pack_with_students_on_it(db_session: Session) -> None:
    service = PackService(db_session)
    pack = service.create(name="X", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"])
    _student(db_session, pack_id=pack.id)
    with pytest.raises(PackInUseError) as exc:
        service.delete(pack.id)
    assert exc.value.code == "pack_in_use"


def test_list_is_ordered_by_offering_then_school_level(db_session: Session) -> None:
    service = PackService(db_session)
    service.create(name="Zeta", level=ClassLevel.AC1, price=Decimal("1"), subjects=["M"])
    service.create(name="Alpha", level=ClassLevel.BAC2, price=Decimal("1"), subjects=["M"])
    service.create(name="Alpha", level=ClassLevel.AC1, price=Decimal("1"), subjects=["M"])
    assert [(p.name, p.level.value) for p in service.list()] == [
        ("Alpha", "1AC"),
        ("Alpha", "2BAC"),
        ("Zeta", "1AC"),
    ]


def test_student_count_for_a_pack(db_session: Session) -> None:
    service = PackService(db_session)
    pack = service.create(name="X", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"])
    _student(db_session, pack_id=pack.id)
    _student(db_session, name="Other")
    assert service.student_count(pack.id) == 1


# --------------------------------------------------------------------------- #
# Remaining edge cases
# --------------------------------------------------------------------------- #


def test_update_rejects_a_negative_price(db_session: Session) -> None:
    service = PackService(db_session)
    pack = service.create(name="X", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"])
    with pytest.raises(InvalidPackError) as exc:
        service.update(pack.id, price=Decimal("-1"))
    assert exc.value.code == "pack_price_negative"


def test_renaming_an_offering_to_its_own_name_is_a_no_op(db_session: Session) -> None:
    service = PackService(db_session)
    _offering(service, "Maths seul")
    service.update_offering("Maths seul", new_name="Maths seul")
    assert {p.name for p in service.list()} == {"Maths seul"}


# --------------------------------------------------------------------------- #
# one pack, one level: editing a pack on its own
# --------------------------------------------------------------------------- #


def _pack(session: Session, name: str = "Pack TC", level: ClassLevel = ClassLevel.TC):
    return PackService(session).create(
        name=name, level=level, price=Decimal("400"), subjects=["Maths", "Physique"]
    )


def test_a_pack_is_renamed_and_its_subjects_changed_on_its_own(db_session: Session) -> None:
    # A pack is one name at one level. Editing it must not reach a same-named pack at another
    # level, which the old offering edit did.
    edited = _pack(db_session, "Pack", ClassLevel.TC)
    other = _pack(db_session, "Pack", ClassLevel.BAC1)
    PackService(db_session).update(edited.id, name="Pack TC Scientifique", subjects=["Maths"])
    assert (edited.name, [s.name for s in edited.subjects]) == ("Pack TC Scientifique", ["Maths"])
    assert (other.name, sorted(s.name for s in other.subjects)) == ("Pack", ["Maths", "Physique"])


def test_a_pack_nobody_is_on_can_change_level(db_session: Session) -> None:
    pack = _pack(db_session)
    PackService(db_session).update(pack.id, level=ClassLevel.BAC1)
    assert pack.level is ClassLevel.BAC1


def test_a_packs_level_is_locked_once_a_student_has_it(db_session: Session) -> None:
    # Otherwise students would silently end up on a pack for another level.
    pack = _pack(db_session)
    _student(db_session, pack_id=pack.id)
    with pytest.raises(InvalidPackError) as exc:
        PackService(db_session).update(pack.id, level=ClassLevel.BAC1)
    assert exc.value.code == "pack_level_locked"
    assert exc.value.params == {"student_count": 1}
    assert pack.level is ClassLevel.TC


def test_keeping_the_same_level_is_not_a_level_change(db_session: Session) -> None:
    pack = _pack(db_session)
    _student(db_session, pack_id=pack.id)
    PackService(db_session).update(pack.id, level=ClassLevel.TC, price=Decimal("450"))
    assert pack.price == Decimal("450")


def test_a_pack_cannot_take_the_name_and_level_of_another(db_session: Session) -> None:
    _pack(db_session, "Pack A", ClassLevel.TC)
    pack = _pack(db_session, "Pack B", ClassLevel.TC)
    with pytest.raises(DuplicatePackError):
        PackService(db_session).update(pack.id, name="Pack A")
    with pytest.raises(DuplicatePackError):
        moved = _pack(db_session, "Pack A", ClassLevel.BAC1)
        PackService(db_session).update(moved.id, level=ClassLevel.TC)


def test_editing_a_pack_cleans_its_name_and_subjects(db_session: Session) -> None:
    pack = _pack(db_session)
    with pytest.raises(InvalidPackError):
        PackService(db_session).update(pack.id, name="   ")
    with pytest.raises(InvalidPackError):
        PackService(db_session).update(pack.id, subjects=[" ", ""])
