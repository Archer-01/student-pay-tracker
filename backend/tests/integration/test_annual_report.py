"""Annual revenue: how much came in, month by month, across a year."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services.payment_service import PaymentService
from app.services.reports_service import ReportsService
from app.services.student_service import StudentService


def _student(session: Session, name: str = "Amina", join: date = date(2023, 1, 5)):
    return StudentService(session).enroll(
        first_name=name, join_date=join, custom_price=Decimal("300")
    )


def test_a_year_always_has_twelve_months(db_session: Session) -> None:
    """Every month is present even with no payments, so a chart has no gaps."""
    report = ReportsService(db_session).annual_report(2023)
    assert [row.month for row in report.months] == list(range(1, 13))
    assert report.total_collected == Decimal("0")
    assert all(row.collected == Decimal("0") for row in report.months)


def test_collected_lands_in_the_month_it_was_paid(db_session: Session) -> None:
    student = _student(db_session)
    payments = PaymentService(db_session)
    payments.record_payment(
        student_id=student.id, cycle_number=0, paid_date=date(2023, 1, 5), amount=Decimal("300")
    )
    payments.record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 3, 20), amount=Decimal("250")
    )
    report = ReportsService(db_session).annual_report(2023)
    by_month = {row.month: row for row in report.months}
    assert by_month[1].collected == Decimal("300")
    assert by_month[2].collected == Decimal("0")
    assert by_month[3].collected == Decimal("250")


def test_total_is_the_sum_of_the_months(db_session: Session) -> None:
    """Holds by construction, so the headline can never disagree with the breakdown."""
    student = _student(db_session)
    payments = PaymentService(db_session)
    for cycle, day in ((0, date(2023, 1, 5)), (1, date(2023, 2, 5)), (2, date(2023, 6, 5))):
        payments.record_payment(
            student_id=student.id, cycle_number=cycle, paid_date=day, amount=Decimal("300")
        )
    report = ReportsService(db_session).annual_report(2023)
    assert report.total_collected == sum(row.collected for row in report.months)
    assert report.total_collected == Decimal("900")


def test_payments_are_counted_per_month(db_session: Session) -> None:
    student = _student(db_session)
    payments = PaymentService(db_session)
    payments.record_payment(
        student_id=student.id, cycle_number=0, paid_date=date(2023, 5, 3), amount=Decimal("300")
    )
    payments.record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 5, 28), amount=Decimal("300")
    )
    report = ReportsService(db_session).annual_report(2023)
    by_month = {row.month: row for row in report.months}
    assert (by_month[5].payments_count, by_month[5].collected) == (2, Decimal("600"))
    assert by_month[6].payments_count == 0
    assert report.payments_count == 2


def test_other_years_are_excluded(db_session: Session) -> None:
    student = _student(db_session, join=date(2022, 12, 5))
    payments = PaymentService(db_session)
    payments.record_payment(
        student_id=student.id, cycle_number=0, paid_date=date(2022, 12, 5), amount=Decimal("300")
    )
    payments.record_payment(
        student_id=student.id, cycle_number=1, paid_date=date(2023, 1, 5), amount=Decimal("300")
    )
    # December of the previous year must not leak into January.
    assert ReportsService(db_session).annual_report(2023).total_collected == Decimal("300")
    assert ReportsService(db_session).annual_report(2022).total_collected == Decimal("300")


def test_december_includes_the_whole_month(db_session: Session) -> None:
    """The year boundary is the obvious place to be off by one."""
    student = _student(db_session, join=date(2023, 12, 1))
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=0, paid_date=date(2023, 12, 31), amount=Decimal("300")
    )
    report = ReportsService(db_session).annual_report(2023)
    assert {row.month: row.collected for row in report.months}[12] == Decimal("300")
    assert report.total_collected == Decimal("300")
