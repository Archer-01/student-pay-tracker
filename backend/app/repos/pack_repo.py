"""Thin CRUD access for packs, subjects, and assignments. No business logic, no date math."""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import ClassLevel, Pack, Subject

# These repos expose a method named `list` (the house convention), which shadows the builtin for
# every annotation declared after it. Aliasing at module scope keeps the later return types
# correct for mypy and at runtime, whatever order the methods end up in.
Packs = list[Pack]
Subjects = list[Subject]


class PackRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, pack: Pack) -> Pack:
        self.session.add(pack)
        self.session.flush()
        return pack

    def get(self, pack_id: int) -> Pack | None:
        return self.session.get(Pack, pack_id)

    def find(self, name: str, level: ClassLevel) -> Pack | None:
        """Look up by the natural key (the unique ``name`` + ``level`` pair)."""
        stmt = select(Pack).where(Pack.name == name, Pack.level == level)
        return self.session.scalars(stmt).one_or_none()

    def list(
        self, *, level: ClassLevel | None = None, active: bool | None = None
    ) -> Packs:
        stmt = select(Pack).options(selectinload(Pack.subjects)).order_by(Pack.id)
        if level is not None:
            stmt = stmt.where(Pack.level == level)
        if active is not None:
            stmt = stmt.where(Pack.is_active == active)
        return list(self.session.scalars(stmt))

    def list_by_name(self, name: str) -> Packs:
        """Every level-variant of one offering — the unit that name/subject edits apply to."""
        stmt = (
            select(Pack)
            .options(selectinload(Pack.subjects))
            .where(Pack.name == name)
            .order_by(Pack.id)
        )
        return list(self.session.scalars(stmt))

    def delete(self, pack: Pack) -> None:
        self.session.delete(pack)
        self.session.flush()


class SubjectRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find(self, name: str) -> Subject | None:
        return self.session.scalars(select(Subject).where(Subject.name == name)).one_or_none()

    def list(self) -> Subjects:
        return list(self.session.scalars(select(Subject).order_by(Subject.name)))

    def create(self, subject: Subject) -> Subject:
        self.session.add(subject)
        self.session.flush()
        return subject
