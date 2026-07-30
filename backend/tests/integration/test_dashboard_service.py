"""Integration test for DashboardService.get_summary — the dashboard math."""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.services.dashboard_service import DashboardService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService


def test_dashboard_summary_math(db_session: Session) -> None:
    students = StudentService(db_session)
    payments = PaymentService(db_session)

    # A (active, fee 300, join Mar 5): pays Apr and May late; Mar & Jun unpaid.
    a = students.enroll(name="A", phone=None, join_date=date(2023, 3, 5), fee=Decimal("300"))
    payments.record_payment(
        student_id=a.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=Decimal("300")
    )
    payments.record_payment(
        student_id=a.id, cycle_number=2, paid_date=date(2023, 5, 10), amount=Decimal("300")
    )

    # B (active, fee 200, join May 5): pays June cycle early (in June); May unpaid.
    b = students.enroll(name="B", phone=None, join_date=date(2023, 5, 5), fee=Decimal("200"))
    payments.record_payment(
        student_id=b.id, cycle_number=1, paid_date=date(2023, 6, 3), amount=Decimal("200")
    )

    # C (INACTIVE): must be excluded from outstanding and latecomers.
    students.enroll(
        name="C",
        phone=None,
        join_date=date(2023, 1, 5),
        fee=Decimal("500"),
        status=StudentStatus.INACTIVE,
    )

    summary = DashboardService(db_session).get_summary(as_of=date(2023, 6, 15))

    # Collected in June: only B's June-3 payment.
    assert summary.total_collected_this_month == Decimal("200")
    # Outstanding: A has 2 unpaid due cycles (Mar, Jun) x 300 = 600; B has 1 (May) x 200 = 200.
    assert summary.total_outstanding == Decimal("800")
    # Latecomers: A drift 10 (5 + 5); B drift 0 (paid early) excluded; C inactive excluded.
    assert [
        (latecomer.name, latecomer.cumulative_drift) for latecomer in summary.top_latecomers
    ] == [("A", 10)]


def test_dashboard_summary_top_n_limit(db_session: Session) -> None:
    students = StudentService(db_session)
    payments = PaymentService(db_session)
    for i in range(4):
        s = students.enroll(
            name=f"S{i}", phone=None, join_date=date(2023, 3, 5), fee=Decimal("100")
        )
        # Each i pays cycle 1 with i+1 days of lateness -> distinct positive drift.
        payments.record_payment(
            student_id=s.id, cycle_number=1, paid_date=date(2023, 4, 6 + i), amount=Decimal("100")
        )

    summary = DashboardService(db_session).get_summary(as_of=date(2023, 5, 1), top_n=2)
    assert len(summary.top_latecomers) == 2
    # Sorted most-drift first.
    drifts = [latecomer.cumulative_drift for latecomer in summary.top_latecomers]
    assert drifts == sorted(drifts, reverse=True)
