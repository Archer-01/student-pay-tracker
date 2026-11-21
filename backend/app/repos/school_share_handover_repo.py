"""Thin CRUD access for :class:`SchoolShareHandover`. No business logic."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SchoolShareHandover


class SchoolShareHandoverRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, year: int, month: int) -> SchoolShareHandover | None:
        stmt = select(SchoolShareHandover).where(
            SchoolShareHandover.year == year, SchoolShareHandover.month == month
        )
        return self.session.scalars(stmt).first()

    def all(self) -> list[SchoolShareHandover]:
        return list(self.session.scalars(select(SchoolShareHandover)))

    def create(self, handover: SchoolShareHandover) -> SchoolShareHandover:
        self.session.add(handover)
        self.session.flush()
        return handover

    def delete(self, handover: SchoolShareHandover) -> None:
        self.session.delete(handover)
        self.session.flush()
