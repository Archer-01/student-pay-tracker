"""Thin CRUD access for :class:`EnrollmentPeriod`. No business logic, no date math."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EnrollmentPeriod

Periods = list[EnrollmentPeriod]


class EnrollmentRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, period: EnrollmentPeriod) -> EnrollmentPeriod:
        self.session.add(period)
        self.session.flush()
        return period

    def get(self, period_id: int) -> EnrollmentPeriod | None:
        return self.session.get(EnrollmentPeriod, period_id)

    def list_for_student(self, student_id: int) -> Periods:
        """Chronological — every rule about ordering and overlap reads from this order."""
        stmt = (
            select(EnrollmentPeriod)
            .where(EnrollmentPeriod.student_id == student_id)
            .order_by(EnrollmentPeriod.entry_date, EnrollmentPeriod.id)
        )
        return list(self.session.scalars(stmt))
