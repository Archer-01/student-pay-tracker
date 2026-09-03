"""PackService — the price list, and the rules that keep an offering's variants coherent.

Because `level` lives on the pack, an offering like "Maths seul" is physically several rows. The
service is what stops them drifting apart: name and subject edits apply to every variant at once.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import ClassLevel
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
    """"Maths" is one row however many packs include it."""
    service = PackService(db_session)
    first = service.create(
        name="A", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths", "Physique"]
    )
    second = service.create(
        name="B", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"]
    )
    maths_ids = {s.id for s in first.subjects if s.name == "Maths"}
    assert maths_ids == {s.id for s in second.subjects if s.name == "Maths"}


def test_duplicate_subject_names_collapse(db_session: Session) -> None:
    pack = PackService(db_session).create(
        name="A", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths", " Maths ", ""]
    )
    assert [s.name for s in pack.subjects] == ["Maths"]


# --------------------------------------------------------------------------- #
# create_offering — the grid row
# --------------------------------------------------------------------------- #


def test_create_offering_makes_one_pack_per_level(db_session: Session) -> None:
    packs = PackService(db_session).create_offering(
        name="Maths seul", subjects=["Maths"], prices=_GRID
    )
    assert {(p.level, p.price) for p in packs} == {
        (ClassLevel.AC1, Decimal("100")),
        (ClassLevel.BAC2, Decimal("150")),
    }


def test_create_offering_shares_one_subject_set(db_session: Session) -> None:
    packs = PackService(db_session).create_offering(
        name="Maths + Physique", subjects=["Maths", "Physique"], prices=_GRID
    )
    assert {tuple(sorted(s.name for s in p.subjects)) for p in packs} == {("Maths", "Physique")}


def test_create_offering_rejects_a_collision(db_session: Session) -> None:
    service = PackService(db_session)
    service.create(name="Maths seul", level=ClassLevel.AC1, price=Decimal("1"), subjects=["M"])
    with pytest.raises(DuplicatePackError):
        service.create_offering(name="Maths seul", subjects=["Maths"], prices=_GRID)


def test_create_offering_requires_prices(db_session: Session) -> None:
    with pytest.raises(InvalidPackError) as exc:
        PackService(db_session).create_offering(name="X", subjects=["Maths"], prices={})
    assert exc.value.code == "pack_no_prices"


# --------------------------------------------------------------------------- #
# update_offering — variants must never diverge
# --------------------------------------------------------------------------- #


def test_editing_subjects_applies_to_every_level_variant(db_session: Session) -> None:
    service = PackService(db_session)
    service.create_offering(name="Maths seul", subjects=["Maths"], prices=_GRID)
    service.update_offering("Maths seul", subjects=["Maths", "Physique"])
    variants = service.list()
    assert len(variants) == 2
    for variant in variants:
        assert sorted(s.name for s in variant.subjects) == ["Maths", "Physique"]


def test_renaming_an_offering_renames_every_variant(db_session: Session) -> None:
    service = PackService(db_session)
    service.create_offering(name="Maths seul", subjects=["Maths"], prices=_GRID)
    service.update_offering("Maths seul", new_name="Maths uniquement")
    assert {p.name for p in service.list()} == {"Maths uniquement"}


def test_renaming_onto_an_existing_offering_is_rejected(db_session: Session) -> None:
    service = PackService(db_session)
    service.create_offering(name="A", subjects=["Maths"], prices=_GRID)
    service.create_offering(name="B", subjects=["Maths"], prices=_GRID)
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
    packs = service.create_offering(name="Maths seul", subjects=["Maths"], prices=_GRID)
    target = next(p for p in packs if p.level is ClassLevel.AC1)
    service.update(target.id, price=Decimal("111"))
    prices = {p.level: p.price for p in service.list()}
    assert prices[ClassLevel.AC1] == Decimal("111")
    assert prices[ClassLevel.BAC2] == Decimal("150")


def test_update_can_deactivate(db_session: Session) -> None:
    service = PackService(db_session)
    pack = service.create(
        name="X", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"]
    )
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
    pack = service.create(
        name="X", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"]
    )
    service.delete(pack.id)
    with pytest.raises(PackNotFoundError):
        service.get(pack.id)


def test_delete_refuses_a_pack_with_students_on_it(db_session: Session) -> None:
    service = PackService(db_session)
    pack = service.create(
        name="X", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"]
    )
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
    pack = service.create(
        name="X", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"]
    )
    _student(db_session, pack_id=pack.id)
    _student(db_session, name="Other")
    assert service.student_count(pack.id) == 1


# --------------------------------------------------------------------------- #
# Remaining edge cases
# --------------------------------------------------------------------------- #


def test_create_offering_rejects_a_negative_price_in_any_cell(db_session: Session) -> None:
    with pytest.raises(InvalidPackError) as exc:
        PackService(db_session).create_offering(
            name="X",
            subjects=["Maths"],
            prices={ClassLevel.AC1: Decimal("100"), ClassLevel.BAC2: Decimal("-1")},
        )
    assert exc.value.code == "pack_price_negative"


def test_update_rejects_a_negative_price(db_session: Session) -> None:
    service = PackService(db_session)
    pack = service.create(
        name="X", level=ClassLevel.AC1, price=Decimal("1"), subjects=["Maths"]
    )
    with pytest.raises(InvalidPackError) as exc:
        service.update(pack.id, price=Decimal("-1"))
    assert exc.value.code == "pack_price_negative"


def test_renaming_an_offering_to_its_own_name_is_a_no_op(db_session: Session) -> None:
    service = PackService(db_session)
    service.create_offering(name="Maths seul", subjects=["Maths"], prices=_GRID)
    service.update_offering("Maths seul", new_name="Maths seul")
    assert {p.name for p in service.list()} == {"Maths seul"}
