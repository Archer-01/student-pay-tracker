"""Report aggregation for the teacher: one month in detail, or a year at a glance.

Data only — no formatting (rendering lives in the API layer). Totals are the sums of the rows they
head, so "total == sum of rows" holds by construction rather than by agreement.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.repos import PaymentRepo, StudentRepo
from app.services.ledger_service import LedgerService
from app.services.pricing_service import PricingService
from app.services.schedule import add_months


@dataclass(frozen=True)
class MonthlyReportRow:
    student_id: int
    name: str
    status: StudentStatus
    fee: Decimal
    collected: Decimal
    cumulative_drift: int
    outstanding: Decimal


@dataclass(frozen=True)
class AnnualMonth:
    """One month of a year, present even when nothing came in."""

    month: int
    collected: Decimal
    payments_count: int


@dataclass(frozen=True)
class AnnualReport:
    year: int
    months: list[AnnualMonth]
    total_collected: Decimal
    payments_count: int


@dataclass(frozen=True)
class MonthlyReport:
    year: int
    month: int
    as_of: date
    total_collected: Decimal
    total_outstanding: Decimal
    rows: list[MonthlyReportRow]


class ReportsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.payments = PaymentRepo(session)
        self.ledger = LedgerService(session)
        self.pricing = PricingService(session)

    def monthly_report(self, year: int, month: int) -> MonthlyReport:
        month_start = date(year, month, 1)
        next_month_start = add_months(month_start, 1)
        as_of = next_month_start - timedelta(days=1)  # last day of the month

        collected_by_student: dict[int, Decimal] = {}
        for payment in self.payments.list_paid_between(month_start, next_month_start):
            collected_by_student[payment.student_id] = (
                collected_by_student.get(payment.student_id, Decimal("0")) + payment.amount
            )

        rows: list[MonthlyReportRow] = []
        for student in self.students.list(status=StudentStatus.ACTIVE):
            entries = self.ledger.get_ledger(student.id, as_of)
            drift = entries[-1].cumulative_drift if entries else 0
            unpaid_due = self.ledger.unpaid_due_dates(student, entries)
            rows.append(
                MonthlyReportRow(
                    student_id=student.id,
                    name=student.full_name,
                    status=student.status,
                    fee=self.pricing.price_of(student),
                    collected=collected_by_student.get(student.id, Decimal("0")),
                    cumulative_drift=drift,
                    outstanding=self.pricing.amount_for_cycles(student, unpaid_due),
                )
            )

        return MonthlyReport(
            year=year,
            month=month,
            as_of=as_of,
            total_collected=sum((row.collected for row in rows), Decimal("0")),
            total_outstanding=sum((row.outstanding for row in rows), Decimal("0")),
            rows=rows,
        )

    def annual_report(self, year: int) -> AnnualReport:
        """What came in over a year, month by month.

        Every month is returned, including empty ones, so callers can chart or tabulate a year
        without filling gaps themselves. Counts money by the date it was *paid*, not the cycle it
        settled — this answers "how much did I take this year", not "what was owed for it".
        """
        collected = [Decimal("0")] * 12
        counts = [0] * 12
        year_start = date(year, 1, 1)
        next_year_start = date(year + 1, 1, 1)
        for payment in self.payments.list_paid_between(year_start, next_year_start):
            index = payment.paid_date.month - 1
            collected[index] += payment.amount
            counts[index] += 1

        months = [
            AnnualMonth(month=index + 1, collected=collected[index], payments_count=counts[index])
            for index in range(12)
        ]
        return AnnualReport(
            year=year,
            months=months,
            total_collected=sum(collected, Decimal("0")),
            payments_count=sum(counts),
        )
