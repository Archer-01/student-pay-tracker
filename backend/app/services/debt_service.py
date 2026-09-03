"""Students who left owing money — and the two ways off that list.

Whether someone "left with debt" is **derived**, never stored: they have no open enrollment
period, and had an outstanding balance as of their last departure. A stored flag would go stale
the moment a payment landed; a derived one resolves itself.

Two routes off the list, and no silent third:

* **They pay.** Recording the payments drops the balance to zero and the flag clears itself.
* **The teacher forgives it.** A :class:`DebtWriteoff` records the amount and a mandatory reason.
  It is deliberately *not* a payment — writing off must never inflate collected revenue, which is
  exactly what recording a fake payment to clear the list would do.

Nothing here blocks anything. Re-admitting a student who owes is the teacher's call (BACKLOG
§2.3); this service's only job is to make the debt impossible to miss.
"""

import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import DebtWriteoff, Student
from app.repos import StudentRepo
from app.services.enrollment_service import EnrollmentService
from app.services.exceptions import InvalidWriteoffError, StudentNotFoundError
from app.services.ledger_service import LedgerService


@dataclass(frozen=True)
class DebtStatus:
    """What a student owed when they walked away."""

    student: Student
    # None while they are still attending — the balance below is then meaningless.
    left_on: date | None
    amount_owed: Decimal
    months_owed: int
    written_off: DebtWriteoff | None

    @property
    def left_with_debt(self) -> bool:
        return self.left_on is not None and self.amount_owed > 0 and self.written_off is None


Statuses = list[DebtStatus]


def _normalize(value: str) -> str:
    """Casefold and strip accents, so "Amïra" and "amira" are the same person."""
    stripped = unicodedata.normalize("NFKD", value)
    return "".join(c for c in stripped if not unicodedata.combining(c)).casefold().strip()


class DebtService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.enrollment = EnrollmentService(session)
        self.ledger = LedgerService(session)

    # -- reads ------------------------------------------------------------- #

    def status(self, student_id: int) -> DebtStatus:
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)
        return self._status_of(student)

    def leavers_with_debt(self) -> Statuses:
        """Everyone who left owing money, largest debt first."""
        statuses = [self._status_of(s) for s in self.students.list()]
        owing = [status for status in statuses if status.left_with_debt]
        return sorted(owing, key=lambda status: status.amount_owed, reverse=True)

    def total_owed(self) -> Decimal:
        return sum((s.amount_owed for s in self.leavers_with_debt()), Decimal("0"))

    def similar_leavers(
        self,
        *,
        phone: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> Statuses:
        """Past leavers who still owe and look like this person.

        The obvious loophole is re-enrolling under a fresh record, so enrolment checks for a
        matching phone number or name. It **warns** rather than blocks: real people share names,
        and refusing an enrolment over a coincidence would be worse than the loophole.
        """
        if not phone and not first_name:
            return []
        wanted_name = _normalize(f"{first_name or ''} {last_name or ''}")
        matches = []
        for status in self.leavers_with_debt():
            student = status.student
            if phone and student.phone and student.phone.strip() == phone.strip():
                matches.append(status)
            elif first_name and _normalize(student.full_name) == wanted_name:
                matches.append(status)
        return matches

    # -- writes ------------------------------------------------------------ #

    def write_off(self, student_id: int, *, reason: str) -> DebtWriteoff:
        """Forgive what a departed student owed, on the record."""
        status = self.status(student_id)
        cleaned = reason.strip()
        if not cleaned:
            raise InvalidWriteoffError("writeoff_reason_empty")
        if not status.left_with_debt:
            raise InvalidWriteoffError("nothing_to_write_off", student_id=student_id)

        writeoff = DebtWriteoff(
            student_id=student_id, amount=status.amount_owed, reason=cleaned
        )
        self.session.add(writeoff)
        self.session.commit()
        return writeoff

    # -- internals --------------------------------------------------------- #

    def _status_of(self, student: Student) -> DebtStatus:
        periods = self.enrollment.history(student.id)
        attending = any(p.leave_date is None for p in periods)
        left_on = (
            None
            if attending
            else max((p.leave_date for p in periods if p.leave_date is not None), default=None)
        )
        if left_on is None:
            return DebtStatus(student, None, Decimal("0"), 0, None)

        # As of the departure: later cycles are suspended by the enrollment gap, so leaving caps
        # the debt at what was owed on the way out rather than letting it grow forever.
        summary = self.ledger.student_summary(student.id, left_on)
        return DebtStatus(
            student=student,
            left_on=left_on,
            amount_owed=summary.amount_owed,
            months_owed=summary.months_overdue,
            written_off=student.writeoffs[0] if student.writeoffs else None,
        )
