"""DashboardService.get_summary — the figures the teacher acts on.

The ranking is by **money owed**, not drift: a student with plenty of drift who is paid up is not
someone to chase. Drift travels on every row and breaks ties.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.services.class_service import ClassService
from app.services.dashboard_service import DashboardService
from app.services.enrollment_service import EnrollmentService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService


def test_dashboard_summary_math(db_session: Session) -> None:
    students = StudentService(db_session)
    payments = PaymentService(db_session)

    # A (active, 300/month, join Mar 5): pays Apr and May late; Mar & Jun unpaid.
    a = students.enroll(
        first_name="A", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("300")
    )
    payments.record_payment(
        student_id=a.id, cycle_number=1, paid_date=date(2023, 4, 10), amount=Decimal("300")
    )
    payments.record_payment(
        student_id=a.id, cycle_number=2, paid_date=date(2023, 5, 10), amount=Decimal("300")
    )

    # B (active, 200/month, join May 5): pays June cycle early; May unpaid.
    b = students.enroll(
        first_name="B", phone=None, join_date=date(2023, 5, 5), custom_price=Decimal("200")
    )
    payments.record_payment(
        student_id=b.id, cycle_number=1, paid_date=date(2023, 6, 3), amount=Decimal("200")
    )

    # C has left: excluded from outstanding and from the chase list.
    c = students.enroll(
        first_name="C", phone=None, join_date=date(2023, 1, 5), custom_price=Decimal("500")
    )
    EnrollmentService(db_session).leave(c.id, leave_date=date(2023, 1, 5))

    summary = DashboardService(db_session).get_summary(as_of=date(2023, 6, 15))

    # Collected in June: only B's June-3 payment.
    assert summary.total_collected_this_month == Decimal("200")
    # A owes Mar + Jun (600); B owes May (200).
    assert summary.total_outstanding == Decimal("800")
    assert summary.active_students == 2
    assert [(d.name, d.amount_owed, d.cumulative_drift) for d in summary.top_debtors] == [
        ("A", Decimal("600"), 10),
        ("B", Decimal("200"), 0),
    ]


def test_debtors_are_ranked_by_money_not_drift(db_session: Session) -> None:
    """The headline case for the rework: lots of drift but nothing owed ranks below real debt."""
    students = StudentService(db_session)
    payments = PaymentService(db_session)

    # Pays everything, always very late: high drift, owes nothing by June.
    late = students.enroll(
        first_name="Late", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("100")
    )
    for cycle, day in ((0, date(2023, 3, 30)), (1, date(2023, 4, 30)), (2, date(2023, 5, 30))):
        payments.record_payment(
            student_id=late.id, cycle_number=cycle, paid_date=day, amount=Decimal("100")
        )

    # Has never paid: no drift at all (drift comes from payments), but owes three months.
    silent = students.enroll(
        first_name="Silent", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("100")
    )

    summary = DashboardService(db_session).get_summary(as_of=date(2023, 5, 31))
    assert [d.name for d in summary.top_debtors] == ["Silent", "Late"]
    assert summary.top_debtors[0].amount_owed > summary.top_debtors[1].amount_owed
    assert summary.top_debtors[1].cumulative_drift > summary.top_debtors[0].cumulative_drift
    assert silent.id and late.id  # both were considered


def test_drift_breaks_ties_on_equal_debt(db_session: Session) -> None:
    students = StudentService(db_session)
    payments = PaymentService(db_session)
    for name, paid_day in (("Tidy", date(2023, 4, 5)), ("Tardy", date(2023, 4, 25))):
        s = students.enroll(
            first_name=name, phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("100")
        )
        payments.record_payment(
            student_id=s.id, cycle_number=1, paid_date=paid_day, amount=Decimal("100")
        )
    summary = DashboardService(db_session).get_summary(as_of=date(2023, 5, 31))
    assert [d.name for d in summary.top_debtors] == ["Tardy", "Tidy"]


def test_the_chase_list_carries_the_class(db_session: Session) -> None:
    from app.models import ClassLevel

    school_class = ClassService(db_session).create(level=ClassLevel.BAC2, name="Groupe A")
    StudentService(db_session).enroll(
        first_name="A", phone=None, join_date=date(2023, 3, 5),
        custom_price=Decimal("100"), class_id=school_class.id,
    )
    summary = DashboardService(db_session).get_summary(as_of=date(2023, 5, 31))
    assert summary.top_debtors[0].class_label == "2BAC — Groupe A"


def test_top_n_limits_the_chase_list(db_session: Session) -> None:
    students = StudentService(db_session)
    for i in range(4):
        students.enroll(
            first_name=f"S{i}", phone=None, join_date=date(2023, 3, 5),
            custom_price=Decimal(str(100 * (i + 1))),
        )
    summary = DashboardService(db_session).get_summary(as_of=date(2023, 5, 1), top_n=2)
    assert len(summary.top_debtors) == 2
    owed = [d.amount_owed for d in summary.top_debtors]
    assert owed == sorted(owed, reverse=True)


# --------------------------------------------------------------------------- #
# Silent problems
# --------------------------------------------------------------------------- #


def test_a_student_with_no_price_is_flagged_as_unbilled(db_session: Session) -> None:
    """No pack and no agreed price means they are invoiced nothing, month after month."""
    students = StudentService(db_session)
    students.enroll(first_name="Unbilled", phone=None, join_date=date(2023, 3, 5))
    students.enroll(
        first_name="Billed", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("100")
    )
    summary = DashboardService(db_session).get_summary(as_of=date(2023, 5, 31))
    assert [d.name for d in summary.unbilled_students] == ["Unbilled"]
    # And they don't muddy the chase list, where they'd sit at zero owed forever.
    assert [d.name for d in summary.top_debtors] == ["Billed"]


def test_a_healthy_database_has_nothing_needing_attention(db_session: Session) -> None:
    StudentService(db_session).enroll(
        first_name="A", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("100")
    )
    summary = DashboardService(db_session).get_summary(as_of=date(2023, 5, 31))
    assert summary.unbilled_students == []
    assert summary.missing_leave_date == []


def test_marked_inactive_but_still_attending_is_flagged(db_session: Session) -> None:
    """The state migration 0006 leaves behind: it refuses to invent a departure date."""
    student = StudentService(db_session).enroll(
        first_name="Legacy", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("100")
    )
    # Simulate the migrated row: status says gone, attendance says present.
    student.status = StudentStatus.INACTIVE
    db_session.flush()
    summary = DashboardService(db_session).get_summary(as_of=date(2023, 5, 31))
    assert [d.name for d in summary.missing_leave_date] == ["Legacy"]


def test_a_properly_departed_student_is_not_flagged(db_session: Session) -> None:
    student = StudentService(db_session).enroll(
        first_name="Gone", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("100")
    )
    EnrollmentService(db_session).leave(student.id, leave_date=date(2023, 4, 30))
    summary = DashboardService(db_session).get_summary(as_of=date(2023, 5, 31))
    assert summary.missing_leave_date == []


def test_a_paid_up_student_is_not_on_the_chase_list(db_session: Session) -> None:
    """Owes nothing and never paid late — there is nothing to do about them."""
    students = StudentService(db_session)
    payments = PaymentService(db_session)
    tidy = students.enroll(
        first_name="Tidy", phone=None, join_date=date(2023, 3, 5), custom_price=Decimal("100")
    )
    for cycle, day in ((0, date(2023, 3, 5)), (1, date(2023, 4, 5))):
        payments.record_payment(
            student_id=tidy.id, cycle_number=cycle, paid_date=day, amount=Decimal("100")
        )
    summary = DashboardService(db_session).get_summary(as_of=date(2023, 4, 30))
    assert summary.top_debtors == []
    assert summary.active_students == 1
