"""Packs: the price list. Create an offering across levels, edit it, retire it.

An *offering* (e.g. "Maths seul") is not a table — it is a pack ``name`` shared by that offering's
level-variants. Since ``level`` sits on the pack, the subject set is physically duplicated across
those variants, so this service is what keeps them identical: subject and name edits always apply
to **every** variant of an offering at once (:meth:`update_offering`), never to one row.
"""

from decimal import Decimal
from typing import Final

from sqlalchemy.orm import Session

from app.models import ClassLevel, Pack, Subject
from app.repos import PackRepo, StudentRepo, SubjectRepo
from app.services.exceptions import (
    DuplicatePackError,
    InvalidPackError,
    PackInUseError,
    PackNotFoundError,
)


class _Unset:
    """Sentinel distinguishing "field omitted" from "field set to None"."""


_UNSET: Final = _Unset()


# `list` is a method name on PackService (the house convention), which shadows the builtin for
# every annotation declared after it. Aliased here, at module scope, so the later signatures stay
# correct for mypy and at runtime. See CLAUDE.md.
Packs = list[Pack]
Subjects = list[Subject]
SubjectNames = list[str]


def _clean_name(name: str, code: str = "pack_name_empty") -> str:
    cleaned = name.strip()
    if not cleaned:
        raise InvalidPackError(code)
    return cleaned


def _clean_subjects(subjects: SubjectNames) -> SubjectNames:
    cleaned = [s.strip() for s in subjects if s.strip()]
    if not cleaned:
        raise InvalidPackError("pack_no_subjects")
    # Preserve order but drop duplicates, so ["Maths", "maths "] can't create two links.
    seen: dict[str, None] = {}
    for name in cleaned:
        seen.setdefault(name, None)
    return list(seen)


class PackService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.packs = PackRepo(session)
        self.subjects = SubjectRepo(session)
        self.students = StudentRepo(session)

    # -- reads ------------------------------------------------------------- #

    def get(self, pack_id: int) -> Pack:
        pack = self.packs.get(pack_id)
        if pack is None:
            raise PackNotFoundError(pack_id)
        return pack

    def list(self, *, level: ClassLevel | None = None, active: bool | None = None) -> Packs:
        """Packs ordered by offering name, then school level."""
        from app.services.class_service import LEVEL_ORDER

        return sorted(
            self.packs.list(level=level, active=active),
            key=lambda p: (p.name, LEVEL_ORDER[p.level]),
        )

    def student_count(self, pack_id: int) -> int:
        return self.students.count_on_pack(pack_id)

    # -- writes ------------------------------------------------------------ #

    def create(
        self, *, name: str, level: ClassLevel, price: Decimal, subjects: SubjectNames
    ) -> Pack:
        """Create one pack (one offering at one level)."""
        cleaned_name = _clean_name(name)
        cleaned_subjects = _clean_subjects(subjects)
        if price < 0:
            raise InvalidPackError("pack_price_negative")
        if self.packs.find(cleaned_name, level) is not None:
            raise DuplicatePackError(cleaned_name, level.value)
        pack = self.packs.create(
            Pack(
                name=cleaned_name,
                level=level,
                price=price,
                subjects=self._resolve_subjects(cleaned_subjects),
            )
        )
        self.session.commit()
        return pack

    def create_offering(
        self, *, name: str, subjects: SubjectNames, prices: dict[ClassLevel, Decimal]
    ) -> Packs:
        """Create every level-variant of an offering in one go, sharing one subject set.

        This is how the price grid creates a row. Doing it per-level through :meth:`create` is
        what lets the variants' subjects drift apart, so the UI never should.
        """
        cleaned_name = _clean_name(name)
        cleaned_subjects = _clean_subjects(subjects)
        if not prices:
            raise InvalidPackError("pack_no_prices")
        for level, price in prices.items():
            if price < 0:
                raise InvalidPackError("pack_price_negative")
            if self.packs.find(cleaned_name, level) is not None:
                raise DuplicatePackError(cleaned_name, level.value)

        resolved = self._resolve_subjects(cleaned_subjects)
        created = [
            self.packs.create(
                Pack(name=cleaned_name, level=level, price=price, subjects=list(resolved))
            )
            for level, price in prices.items()
        ]
        self.session.commit()
        return created

    def update(
        self,
        pack_id: int,
        *,
        price: Decimal | _Unset = _UNSET,
        is_active: bool | _Unset = _UNSET,
    ) -> Pack:
        """Edit one cell of the grid: this pack's price and/or whether it's offered.

        Name and subjects are deliberately **not** editable here — they belong to the offering as
        a whole (:meth:`update_offering`). Changing ``price`` immediately changes what every
        student on this pack pays, including for months they have not yet paid.
        """
        pack = self.get(pack_id)
        if not isinstance(price, _Unset):
            if price < 0:
                raise InvalidPackError("pack_price_negative")
            pack.price = price
        if not isinstance(is_active, _Unset):
            pack.is_active = is_active
        self.session.commit()
        return pack

    def update_offering(
        self,
        name: str,
        *,
        new_name: str | _Unset = _UNSET,
        subjects: SubjectNames | _Unset = _UNSET,
    ) -> Packs:
        """Rename an offering and/or change its subjects, across **all** its level-variants."""
        variants = self.packs.list_by_name(name)
        if not variants:
            raise InvalidPackError("pack_offering_unknown", name=name)

        if not isinstance(new_name, _Unset):
            cleaned = _clean_name(new_name)
            if cleaned != name:
                for variant in variants:
                    if self.packs.find(cleaned, variant.level) is not None:
                        raise DuplicatePackError(cleaned, variant.level.value)
                for variant in variants:
                    variant.name = cleaned

        if not isinstance(subjects, _Unset):
            resolved = self._resolve_subjects(_clean_subjects(subjects))
            for variant in variants:
                variant.subjects = list(resolved)

        self.session.commit()
        return variants

    def delete(self, pack_id: int) -> None:
        """Delete a pack no student is on. Otherwise: deactivate it instead."""
        pack = self.get(pack_id)
        count = self.students.count_on_pack(pack_id)
        if count:
            raise PackInUseError(pack_id, count)
        self.packs.delete(pack)
        self.session.commit()

    # -- internals --------------------------------------------------------- #

    def _resolve_subjects(self, names: SubjectNames) -> Subjects:
        """Get-or-create each subject by name, so the teacher never curates a subject list."""
        resolved: Subjects = []
        for name in names:
            subject = self.subjects.find(name)
            if subject is None:
                subject = self.subjects.create(Subject(name=name))
            resolved.append(subject)
        return resolved
