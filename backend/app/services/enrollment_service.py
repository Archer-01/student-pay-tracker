"""Leaving and returning — when a student was actually attending.

The billing schedule is generated from ``student.join_date`` forever. Periods never move that
anchor; they record presence, so months a student was away can be excluded from what they owe
**without** rewriting their history. That distinction is the whole design: a student who leaves
owing three months and comes back still owes three months.

Rules enforced here (the database backs up only the first two):

* dates within a period are ordered (``leave_date >= entry_date``) — CHECK constraint
* at most one open period per student — partial unique index
* periods never overlap, and are strictly ordered
* the first period starts on ``join_date``; moving it would fork the schedule
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models import EnrollmentPeriod, Student, StudentStatus
from app.repos import EnrollmentRepo, StudentRepo
from app.services.exceptions import InvalidPeriodError, StudentNotFoundError

Periods = list[EnrollmentPeriod]


class EnrollmentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.periods = EnrollmentRepo(session)
        self.students = StudentRepo(session)

    # -- reads ------------------------------------------------------------- #

    def history(self, student_id: int) -> Periods:
        """Every period the student has had, oldest first."""
        self._require_student(student_id)
        return self.periods.list_for_student(student_id)

    def open_period(self, student_id: int) -> EnrollmentPeriod | None:
        return next(
            (p for p in self.periods.list_for_student(student_id) if p.leave_date is None), None
        )

    def is_attending(self, student_id: int) -> bool:
        return self.open_period(student_id) is not None

    # -- writes ------------------------------------------------------------ #

    def start(self, student: Student) -> EnrollmentPeriod:
        """Open the first period, at the anchor. Called when a student is enrolled."""
        return self.periods.create(
            EnrollmentPeriod(student_id=student.id, entry_date=student.join_date)
        )

    def leave(
        self, student_id: int, *, leave_date: date, reason: str | None = None
    ) -> EnrollmentPeriod:
        """Record a departure by closing the open period."""
        self._require_student(student_id)
        period = self.open_period(student_id)
        if period is None:
            raise InvalidPeriodError("period_not_open", student_id=student_id)
        if leave_date < period.entry_date:
            raise InvalidPeriodError(
                "leave_before_entry",
                leave_date=leave_date,
                entry_date=period.entry_date,
            )
        period.leave_date = leave_date
        period.leave_reason = reason
        self._sync_status(student_id)
        self.session.commit()
        return period

    def return_(self, student_id: int, *, entry_date: date) -> EnrollmentPeriod:
        """Record a return by opening a new period. The anchor is untouched."""
        self._require_student(student_id)
        existing = self.periods.list_for_student(student_id)
        if any(p.leave_date is None for p in existing):
            raise InvalidPeriodError("period_already_open", student_id=student_id)
        last_leave = max((p.leave_date for p in existing if p.leave_date is not None), default=None)
        if last_leave is not None and entry_date < last_leave:
            raise InvalidPeriodError(
                "return_before_leave",
                entry_date=entry_date,
                leave_date=last_leave,
            )
        period = self.periods.create(EnrollmentPeriod(student_id=student_id, entry_date=entry_date))
        self._sync_status(student_id)
        self.session.commit()
        return period

    # -- internals --------------------------------------------------------- #

    def _sync_status(self, student_id: int) -> None:
        """Keep ``student.status`` in step with the periods.

        The periods are the source of truth; ``status`` is a cached answer to "is there an open
        period", kept for the cheap ``?status=active`` filter. This method is its only writer —
        `StudentUpdate` deliberately doesn't accept `status`, so the two cannot drift apart.
        """
        student = self.students.get(student_id)
        assert student is not None
        attending = any(p.leave_date is None for p in self.periods.list_for_student(student_id))
        student.status = StudentStatus.ACTIVE if attending else StudentStatus.INACTIVE

    def _require_student(self, student_id: int) -> None:
        if self.students.get(student_id) is None:
            raise StudentNotFoundError(student_id)
