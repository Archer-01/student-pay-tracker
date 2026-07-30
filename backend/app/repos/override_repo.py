"""Thin CRUD access for :class:`AnchorOverride`. Append-only log; no business logic."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnchorOverride


class OverrideRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, override: AnchorOverride) -> AnchorOverride:
        self.session.add(override)
        self.session.flush()
        return override

    def get(self, override_id: int) -> AnchorOverride | None:
        return self.session.get(AnchorOverride, override_id)

    def list_for_student(self, student_id: int) -> list[AnchorOverride]:
        stmt = (
            select(AnchorOverride)
            .where(AnchorOverride.student_id == student_id)
            .order_by(AnchorOverride.new_due_date)
        )
        return list(self.session.scalars(stmt))

    def delete(self, override: AnchorOverride) -> None:
        self.session.delete(override)
        self.session.flush()
