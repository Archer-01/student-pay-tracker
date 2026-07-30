"""Recording payments — where the drift math meets the database.

``record_payment`` computes the cycle's expected due date (override-aware) and the resulting
``days_late`` and **freezes** both onto the payment row. Once written they are never
recomputed, so a later override can never rewrite recorded history.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Payment
from app.repos import OverrideRepo, PaymentRepo, StudentRepo
from app.services.exceptions import DuplicatePaymentError, StudentNotFoundError
from app.services.schedule import cycle_number_for_month, days_late, expected_due_date_for_cycle


class PaymentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.payments = PaymentRepo(session)
        self.overrides = OverrideRepo(session)

    def cycle_for_month(self, student_id: int, year: int, month: int) -> int:
        """Resolve a calendar month to its cycle number for a student (override-aware)."""
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)
        override_dates = [o.new_due_date for o in self.overrides.list_for_student(student_id)]
        return cycle_number_for_month(student.join_date, year, month, override_dates)

    def record_payment(
        self, *, student_id: int, cycle_number: int, paid_date: date, amount: Decimal
    ) -> Payment:
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)

        if self.payments.get_by_student_cycle(student_id, cycle_number) is not None:
            raise DuplicatePaymentError(student_id, cycle_number)

        override_dates = [o.new_due_date for o in self.overrides.list_for_student(student_id)]
        expected = expected_due_date_for_cycle(student.join_date, cycle_number, override_dates)

        payment = Payment(
            student_id=student_id,
            cycle_number=cycle_number,
            paid_date=paid_date,
            expected_due_date=expected,
            days_late=days_late(expected, paid_date),
            amount=amount,
        )
        self.payments.create(payment)
        self.session.commit()
        return payment
