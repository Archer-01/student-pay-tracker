"""Monthly report aggregation for the teacher.

Data only — no formatting (CSV rendering lives in the API layer). Lists active students; totals
are the sums of the per-student rows, so "total == sum of rows" holds by construction.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.repos import PaymentRepo, StudentRepo
from app.services.ledger_service import LedgerService
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
            unpaid_due = sum(1 for e in entries if e.paid_date is None)
            rows.append(
                MonthlyReportRow(
                    student_id=student.id,
                    name=student.name,
                    status=student.status,
                    fee=student.fee,
                    collected=collected_by_student.get(student.id, Decimal("0")),
                    cumulative_drift=drift,
                    outstanding=unpaid_due * student.fee,
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
