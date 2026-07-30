"""Anchor overrides — an audit log of agreed due-date changes.

An override permanently re-anchors the schedule from its month forward. It is append-only:
``create_override`` never touches ``student.join_date`` or existing payment rows, so it can
never retroactively reduce drift for cycles before it.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import AnchorOverride
from app.repos import OverrideRepo, StudentRepo
from app.services.exceptions import InvalidOverrideError, StudentNotFoundError


class OverrideService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.overrides = OverrideRepo(session)

    def create_override(
        self, *, student_id: int, new_due_date: date, reason: str
    ) -> AnchorOverride:
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)

        if not reason.strip():
            raise InvalidOverrideError("override_reason_empty")

        if new_due_date <= student.join_date:
            raise InvalidOverrideError("override_before_join")

        # No backward re-anchor: an override's month must not precede an existing one's month,
        # which would let it reach back and alter earlier cycles. Same month = last-wins fix.
        existing = self.overrides.list_for_student(student_id)
        if existing:
            latest = max(existing, key=lambda o: (o.new_due_date.year, o.new_due_date.month))
            new_key = (new_due_date.year, new_due_date.month)
            latest_key = (latest.new_due_date.year, latest.new_due_date.month)
            if new_key < latest_key:
                raise InvalidOverrideError("override_backwards")

        override = AnchorOverride(student_id=student_id, new_due_date=new_due_date, reason=reason)
        self.overrides.create(override)
        self.session.commit()
        return override
