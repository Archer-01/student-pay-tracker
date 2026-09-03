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
from typing import Final

from sqlalchemy.orm import Session

from app.models import EnrollmentPeriod, Student, StudentStatus
from app.repos import EnrollmentRepo, StudentRepo
from app.services.exceptions import InvalidPeriodError, StudentNotFoundError

Periods = list[EnrollmentPeriod]


class _Unset:
    """Sentinel distinguishing "field omitted" from "field set to None"."""


_UNSET: Final = _Unset()


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
                leave_date=leave_date.isoformat(),
                entry_date=period.entry_date.isoformat(),
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
        last_leave = max(
            (p.leave_date for p in existing if p.leave_date is not None), default=None
        )
        if last_leave is not None and entry_date < last_leave:
            raise InvalidPeriodError(
                "return_before_leave",
                entry_date=entry_date.isoformat(),
                leave_date=last_leave.isoformat(),
            )
        period = self.periods.create(
            EnrollmentPeriod(student_id=student_id, entry_date=entry_date)
        )
        self._sync_status(student_id)
        self.session.commit()
        return period

    def amend(
        self,
        student_id: int,
        period_id: int,
        *,
        entry_date: date | _Unset = _UNSET,
        leave_date: date | None | _Unset = _UNSET,
        reason: str | None | _Unset = _UNSET,
    ) -> EnrollmentPeriod:
        """Correct a mistyped date, re-validating every ordering rule first.

        Validation runs against the *proposed* timeline before anything is written: mutating and
        then checking would let SQLAlchemy autoflush the bad row into the database, where the
        CHECK constraint reports it as an IntegrityError instead of a domain error — and would
        leave the session holding a dirty object after a rejected amendment.
        """
        self._require_student(student_id)
        period = self.periods.get(period_id)
        if period is None or period.student_id != student_id:
            raise InvalidPeriodError("period_not_found", period_id=period_id)

        history = self.periods.list_for_student(student_id)
        new_entry = period.entry_date if isinstance(entry_date, _Unset) else entry_date
        new_leave = period.leave_date if isinstance(leave_date, _Unset) else leave_date

        if period.id == history[0].id and new_entry != self._anchor(student_id):
            raise InvalidPeriodError("first_entry_is_the_anchor")
        if new_leave is not None and new_leave < new_entry:
            raise InvalidPeriodError(
                "leave_before_entry",
                leave_date=new_leave.isoformat(),
                entry_date=new_entry.isoformat(),
            )
        self._check_timeline(
            sorted(
                (
                    (new_entry, new_leave) if p.id == period.id else (p.entry_date, p.leave_date)
                    for p in history
                ),
                key=lambda span: span[0],
            )
        )

        period.entry_date = new_entry
        period.leave_date = new_leave
        if not isinstance(reason, _Unset):
            period.leave_reason = reason
        self._sync_status(student_id)
        self.session.commit()
        return period

    # -- internals --------------------------------------------------------- #

    def _anchor(self, student_id: int) -> date:
        student = self.students.get(student_id)
        assert student is not None  # _require_student ran first
        return student.join_date

    @staticmethod
    def _check_timeline(spans: list[tuple[date, date | None]]) -> None:
        """Reject a proposed set of (entry, leave) spans that would overlap or run out of order."""
        for earlier, later in zip(spans, spans[1:], strict=False):
            # An open period can only be the last one, so a missing leave date here overlaps.
            if earlier[1] is None or later[0] < earlier[1]:
                raise InvalidPeriodError("periods_overlap")

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
