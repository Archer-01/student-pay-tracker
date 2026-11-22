"""Recording payments — where the drift math meets the database.

``record_payment`` computes the cycle's expected due date (override-aware) and the resulting
``days_late`` and **freezes** both onto the payment row. Once written they are never
recomputed, so a later override can never rewrite recorded history.

Corrections are a different thing from recomputation: when the teacher typed the wrong amount or
date, ``update_payment`` fixes exactly that. The frozen due date never moves, and lateness is
re-derived from it only when the paid date itself was the mistake.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Payment, Student
from app.repos import OverrideRepo, PaymentRepo, StudentRepo
from app.services.exceptions import (
    DuplicatePaymentError,
    InvalidPaymentError,
    PaymentNotFoundError,
    StudentNotFoundError,
)
from app.services.pricing_service import PricingService
from app.services.schedule import cycle_number_for_month, days_late, expected_due_date_for_cycle

_CENTS = Decimal("0.01")


def _check_paid_date(paid_date: date, today: date | None) -> None:
    """A payment can't be dated in the future: it would count as days late that never happened.

    Here rather than only in the API's request schema, so every caller gets it (decision 0008).
    """
    if paid_date > (today or date.today()):
        raise InvalidPaymentError("payment_date_in_future", paid_date=paid_date)


class PaymentService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.payments = PaymentRepo(session)
        self.overrides = OverrideRepo(session)
        self.pricing = PricingService(session)

    def _require_student(self, student_id: int) -> Student:
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)
        return student

    def _check_amount(self, student: Student, amount: Decimal) -> None:
        """A payment is real money, and never more than the student's monthly price.

        The cap catches the slip it exists for: typing another student's price, or the pack's,
        instead of this student's. Paying *less* is normal (part of a month, the rest owed). A
        student with no price at all (no pack, no agreed price) has nothing to compare against.
        """
        if amount <= 0:
            raise InvalidPaymentError("payment_amount_not_positive")
        if amount != amount.quantize(_CENTS):
            # The column keeps two decimals and would round silently ("0.004" stored as 0.00).
            raise InvalidPaymentError("payment_amount_precision")
        price = self.pricing.price_of(student)
        if price > 0 and amount > price:
            # Quoted to the cent so a typed "350" and a stored "300.00" read alike in the message.
            raise InvalidPaymentError(
                "payment_exceeds_price",
                amount=amount.quantize(_CENTS),
                price=price.quantize(_CENTS),
            )

    def cycle_for_month(self, student_id: int, year: int, month: int) -> int:
        """Resolve a calendar month to its cycle number for a student (override-aware)."""
        student = self.students.get(student_id)
        if student is None:
            raise StudentNotFoundError(student_id)
        override_dates = [o.new_due_date for o in self.overrides.list_for_student(student_id)]
        return cycle_number_for_month(student.join_date, year, month, override_dates)

    def record_payment(
        self,
        *,
        student_id: int,
        cycle_number: int,
        paid_date: date,
        amount: Decimal,
        today: date | None = None,
    ) -> Payment:
        student = self._require_student(student_id)
        _check_paid_date(paid_date, today)
        if self.pricing.price_status(student) == "free":
            # Their cap is their price, 0 (decision 0014). Corrections to a payment taken before
            # they were free stay possible: only new money is refused.
            raise InvalidPaymentError("payment_student_free")
        self._check_amount(student, amount)

        override_dates = [o.new_due_date for o in self.overrides.list_for_student(student_id)]
        expected = expected_due_date_for_cycle(student.join_date, cycle_number, override_dates)

        existing = self.payments.get_by_student_cycle(student_id, cycle_number)
        if existing is not None:
            raise DuplicatePaymentError(student_id, cycle_number, existing.expected_due_date)

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

    def get_payment(self, *, student_id: int, cycle_number: int) -> Payment:
        self._require_student(student_id)
        payment = self.payments.get_by_student_cycle(student_id, cycle_number)
        if payment is None:
            raise PaymentNotFoundError(student_id, cycle_number)
        return payment

    def update_payment(
        self,
        *,
        student_id: int,
        cycle_number: int,
        amount: Decimal | None = None,
        paid_date: date | None = None,
        today: date | None = None,
    ) -> Payment:
        """Correct a recorded payment's amount and/or paid date; ``None`` leaves a field alone.

        Only a changed amount is checked against the cap. Pricing is current, not historical, so
        a payment genuinely made before a price cut can exceed today's price, and fixing its date
        must not be blocked by an amount nobody is touching. A student free now has no price to
        compare with, so their old payment can be lowered, never raised (decision 0014).
        """
        payment = self.get_payment(student_id=student_id, cycle_number=cycle_number)
        # "Changed" by value: the same amount sent again (the CLI sends every field) isn't one.
        if amount is not None and amount != payment.amount:
            self._check_amount(payment.student, amount)
            free = self.pricing.price_status(payment.student) == "free"
            if free and amount > payment.amount:
                raise InvalidPaymentError(
                    "payment_raised_for_free_student", recorded=payment.amount.quantize(_CENTS)
                )
            payment.amount = amount
        if paid_date is not None:
            _check_paid_date(paid_date, today)
            payment.paid_date = paid_date
            payment.days_late = days_late(payment.expected_due_date, paid_date)
        self.session.commit()
        return payment

    def delete_payment(self, *, student_id: int, cycle_number: int) -> None:
        """Remove a payment — the way to move one recorded against the wrong month."""
        payment = self.get_payment(student_id=student_id, cycle_number=cycle_number)
        self.payments.delete(payment)
        self.session.commit()
