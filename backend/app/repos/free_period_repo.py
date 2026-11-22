"""Thin CRUD access for :class:`FreePeriod`. No business logic, no date math."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FreePeriod

FreePeriods = list[FreePeriod]


class FreePeriodRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, period: FreePeriod) -> FreePeriod:
        self.session.add(period)
        self.session.flush()
        return period

    def delete(self, period: FreePeriod) -> None:
        self.session.delete(period)
        self.session.flush()

    def list_for_student(self, student_id: int) -> FreePeriods:
        stmt = (
            select(FreePeriod)
            .where(FreePeriod.student_id == student_id)
            .order_by(FreePeriod.from_date, FreePeriod.id)
        )
        return list(self.session.scalars(stmt))

    def open_for(self, student_id: int) -> FreePeriod | None:
        stmt = select(FreePeriod).where(
            FreePeriod.student_id == student_id, FreePeriod.to_date.is_(None)
        )
        return self.session.scalars(stmt).first()
