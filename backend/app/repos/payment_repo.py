"""Thin CRUD access for :class:`Payment`. No business logic, no date math.

``get_by_student_cycle`` is just a SELECT that the Sprint 3 service will use to detect
duplicate payments; the rejection *decision* lives in the service, not here.
"""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Payment


class PaymentRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payment: Payment) -> Payment:
        self.session.add(payment)
        self.session.flush()
        return payment

    def bulk_create(self, payments: Sequence[Payment]) -> list[Payment]:
        self.session.add_all(payments)
        self.session.flush()
        return list(payments)

    def get(self, payment_id: int) -> Payment | None:
        return self.session.get(Payment, payment_id)

    def get_by_student_cycle(self, student_id: int, cycle_number: int) -> Payment | None:
        stmt = select(Payment).where(
            Payment.student_id == student_id,
            Payment.cycle_number == cycle_number,
        )
        return self.session.scalars(stmt).one_or_none()

    def list_for_student(self, student_id: int) -> list[Payment]:
        stmt = (
            select(Payment).where(Payment.student_id == student_id).order_by(Payment.cycle_number)
        )
        return list(self.session.scalars(stmt))

    def list_paid_between(self, start: date, end: date) -> list[Payment]:
        """Payments whose paid_date is in the half-open range [start, end), ordered by date."""
        stmt = (
            select(Payment)
            .where(Payment.paid_date >= start, Payment.paid_date < end)
            .order_by(Payment.paid_date)
        )
        return list(self.session.scalars(stmt))

    def delete(self, payment: Payment) -> None:
        self.session.delete(payment)
        self.session.flush()
