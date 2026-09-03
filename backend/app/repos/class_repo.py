"""Thin CRUD access for :class:`SchoolClass`. No business logic, no ordering policy."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClassLevel, SchoolClass


class ClassRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, school_class: SchoolClass) -> SchoolClass:
        self.session.add(school_class)
        self.session.flush()
        return school_class

    def get(self, class_id: int) -> SchoolClass | None:
        return self.session.get(SchoolClass, class_id)

    def find(self, level: ClassLevel, name: str) -> SchoolClass | None:
        """Look up by the natural key (the unique ``level`` + ``name`` pair)."""
        stmt = select(SchoolClass).where(
            SchoolClass.level == level, SchoolClass.name == name
        )
        return self.session.scalars(stmt).one_or_none()

    def list(self, *, level: ClassLevel | None = None) -> list[SchoolClass]:
        """All classes, insertion-ordered. Display ordering (school order) is the service's job."""
        stmt = select(SchoolClass).order_by(SchoolClass.id)
        if level is not None:
            stmt = stmt.where(SchoolClass.level == level)
        return list(self.session.scalars(stmt))

    def delete(self, school_class: SchoolClass) -> None:
        self.session.delete(school_class)
        self.session.flush()
