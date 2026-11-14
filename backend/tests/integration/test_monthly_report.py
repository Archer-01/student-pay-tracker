"""The monthly report's totals agree with every other place that counts money received."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services.dashboard_service import DashboardService
from app.services.enrollment_service import EnrollmentService
from app.services.payment_service import PaymentService
from app.services.reports_service import ReportsService
from app.services.student_service import StudentService


def _paid_october_then_left(db_session: Session) -> tuple[int, int]:
    """One student still here, one who paid October and left in November."""
    students = StudentService(db_session)
    payments = PaymentService(db_session)
    stays = students.enroll(
        first_name="Amina", phone=None, join_date=date(2026, 9, 5), custom_price=Decimal("240")
    )
    leaves = students.enroll(
        first_name="Omar", phone=None, join_date=date(2026, 9, 5), custom_price=Decimal("200")
    )
    payments.record_payment(
        student_id=stays.id, cycle_number=1, paid_date=date(2026, 10, 5), amount=Decimal("240")
    )
    payments.record_payment(
        student_id=leaves.id, cycle_number=1, paid_date=date(2026, 10, 6), amount=Decimal("200")
    )
    EnrollmentService(db_session).leave(leaves.id, leave_date=date(2026, 11, 2))
    return stays.id, leaves.id


def test_money_from_a_student_who_has_since_left_still_counts(db_session: Session) -> None:
    # The money came in in October; leaving in November doesn't take it back out. Counting only
    # current students made October's total shrink after the fact.
    _paid_october_then_left(db_session)
    report = ReportsService(db_session).monthly_report(2026, 10)
    assert report.total_collected == Decimal("440")


def test_a_student_who_paid_that_month_is_listed_even_after_leaving(db_session: Session) -> None:
    _, left = _paid_october_then_left(db_session)
    rows = {r.student_id: r for r in ReportsService(db_session).monthly_report(2026, 10).rows}
    assert rows[left].collected == Decimal("200")


def test_the_month_agrees_with_the_year_and_with_the_dashboard(db_session: Session) -> None:
    # Bilan's month, Bilan's year and Accueil show the same "collected" for the same month.
    _paid_october_then_left(db_session)
    reports = ReportsService(db_session)
    month = reports.monthly_report(2026, 10).total_collected
    assert month == reports.annual_report(2026).months[9].collected
    assert (
        month
        == DashboardService(db_session).get_summary(date(2026, 10, 31)).total_collected_this_month
    )


def test_a_former_student_who_paid_nothing_that_month_stays_off_the_list(
    db_session: Session,
) -> None:
    _, left = _paid_october_then_left(db_session)
    rows = {r.student_id for r in ReportsService(db_session).monthly_report(2026, 11).rows}
    assert left not in rows


def test_the_school_share_is_counted_on_the_same_money_everywhere(db_session: Session) -> None:
    # 440 came in in October; at 25% the school's part is 110 on Bilan's month, Bilan's year
    # and Accueil alike.
    _paid_october_then_left(db_session)
    reports = ReportsService(db_session)
    month = reports.monthly_report(2026, 10, share_percent=Decimal("25")).share
    year = reports.annual_report(2026, share_percent=Decimal("25"))
    dash = DashboardService(db_session).get_summary(date(2026, 10, 31), share_percent=Decimal("25"))
    assert (month.school, month.teacher) == (Decimal("110.00"), Decimal("330.00"))
    assert year.months[9].share == month
    assert year.share.school == Decimal("110.00")
    assert dash.share_this_month == month


def test_without_a_share_everything_is_the_teachers(db_session: Session) -> None:
    _paid_october_then_left(db_session)
    share = ReportsService(db_session).monthly_report(2026, 10).share
    assert (share.percent, share.school, share.teacher) == (
        Decimal("0"),
        Decimal("0.00"),
        Decimal("440"),
    )
