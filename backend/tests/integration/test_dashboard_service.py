"""DashboardService.get_summary — the figures the teacher acts on.

The ranking is by **money owed**, not drift: a student with plenty of drift who is paid up is not
someone to chase. Drift travels on every row and breaks ties.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import StudentStatus
from app.repos import PaymentRepo
from app.services.class_service import ClassService
from app.services.dashboard_service import DashboardService
from app.services.enrollment_service import EnrollmentService
from app.services.override_service import OverrideService
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
        first_name="A",
        phone=None,
        join_date=date(2023, 3, 5),
        custom_price=Decimal("100"),
        class_id=school_class.id,
    )
    summary = DashboardService(db_session).get_summary(as_of=date(2023, 5, 31))
    assert summary.top_debtors[0].class_label == "2BAC — Groupe A"


def test_top_n_limits_the_chase_list(db_session: Session) -> None:
    students = StudentService(db_session)
    for i in range(4):
        students.enroll(
            first_name=f"S{i}",
            phone=None,
            join_date=date(2023, 3, 5),
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


# --------------------------------------------------------------------------- #
# This month's dues, and who is due this week
# --------------------------------------------------------------------------- #

_NOV_14 = date(2026, 11, 14)


def _student(db_session: Session, name: str, joined: date, price: str = "200") -> int:
    return (
        StudentService(db_session)
        .enroll(first_name=name, join_date=joined, custom_price=Decimal(price))
        .id
    )


def _pay(db_session: Session, sid: int, cycle: int, on: date, amount: str = "200") -> None:
    PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=cycle, paid_date=on, amount=Decimal(amount)
    )


def test_this_months_dues_count_whoever_is_due_this_month(db_session: Session) -> None:
    # Due on the 5th: November's 200 is paid. Due on the 25th: not yet, but it is this
    # month's, so it counts toward what's expected.
    early = _student(db_session, "Early", date(2026, 9, 5))
    for cycle, day in ((0, date(2026, 9, 5)), (1, date(2026, 10, 5)), (2, date(2026, 11, 6))):
        _pay(db_session, early, cycle, day)
    late = _student(db_session, "Late", date(2026, 9, 25), price="300")
    _pay(db_session, late, 0, date(2026, 9, 25), "300")
    _pay(db_session, late, 1, date(2026, 10, 25), "300")

    month = DashboardService(db_session).get_summary(_NOV_14).this_month
    assert (month.expected, month.settled) == (Decimal("500"), Decimal("200"))
    assert (month.students_expected, month.students_settled) == (2, 1)


def test_a_month_paid_in_advance_or_below_the_price_counts_what_was_paid(
    db_session: Session,
) -> None:
    sid = _student(db_session, "Ahead", date(2026, 9, 25))
    _pay(db_session, sid, 0, date(2026, 9, 25))
    _pay(db_session, sid, 1, date(2026, 10, 25))
    _pay(db_session, sid, 2, date(2026, 11, 10), "150")  # November, early and a little short

    # A paid month counts what was paid on both sides: a student who pays below their price
    # is settled, and the bar reaches the end when everyone has paid.
    month = DashboardService(db_session).get_summary(_NOV_14).this_month
    assert (month.expected, month.settled) == (Decimal("150"), Decimal("150"))
    assert month.students_settled == 1


def test_months_away_and_students_not_billed_are_not_expected(db_session: Session) -> None:
    # Away from 20 October to 10 November: the 5 November due falls in the gap.
    away = _student(db_session, "Away", date(2026, 9, 5))
    _pay(db_session, away, 0, date(2026, 9, 5))
    _pay(db_session, away, 1, date(2026, 10, 5))
    enrollment = EnrollmentService(db_session)
    enrollment.leave(away, leave_date=date(2026, 10, 20))
    enrollment.return_(away, entry_date=date(2026, 11, 10))
    StudentService(db_session).enroll(first_name="Free", join_date=date(2026, 9, 5))

    month = DashboardService(db_session).get_summary(_NOV_14).this_month
    assert (month.expected, month.students_expected) == (Decimal("0"), 0)


def test_due_this_week_runs_from_today_to_six_days_ahead(db_session: Session) -> None:
    today = _student(db_session, "Today", date(2026, 9, 14))
    in_six = _student(db_session, "InSix", date(2026, 9, 20), price="300")
    _student(db_session, "InSeven", date(2026, 9, 21))
    paid = _student(db_session, "PaidAhead", date(2026, 9, 16))
    _pay(db_session, paid, 2, date(2026, 11, 12))
    for sid, day in ((today, 14), (in_six, 20)):
        _pay(db_session, sid, 0, date(2026, 9, day), "300" if sid == in_six else "200")
        _pay(db_session, sid, 1, date(2026, 10, day), "300" if sid == in_six else "200")

    soon = DashboardService(db_session).get_summary(_NOV_14).due_this_week
    assert [(d.name, d.due_date, d.amount) for d in soon] == [
        ("Today", date(2026, 11, 14), Decimal("200")),
        ("InSix", date(2026, 11, 20), Decimal("300")),
    ]


def test_a_moved_payment_day_moves_the_due_into_the_right_week(db_session: Session) -> None:
    sid = _student(db_session, "Moved", date(2026, 9, 5))
    _pay(db_session, sid, 0, date(2026, 9, 5))
    _pay(db_session, sid, 1, date(2026, 10, 5))
    # From November the student pays on the 16th instead of the 5th.
    OverrideService(db_session).create_override(
        student_id=sid, new_due_date=date(2026, 11, 16), reason="Paie après le salaire"
    )
    summary = DashboardService(db_session).get_summary(_NOV_14)
    assert [(d.name, d.due_date) for d in summary.due_this_week] == [("Moved", date(2026, 11, 16))]
    assert summary.this_month.expected == Decimal("200")


def test_the_home_page_reminds_of_last_months_share_until_handed_over(db_session: Session) -> None:
    sid = _student(db_session, "Amina", date(2026, 9, 5), price="240")
    _pay(db_session, sid, 1, date(2026, 10, 5), "240")
    quarter = Decimal("25")
    summary = DashboardService(db_session).get_summary(_NOV_14, share_percent=quarter)
    pending = summary.school_share_pending
    assert pending is not None and (pending.month, pending.remaining) == (10, Decimal("60.00"))
    assert DashboardService(db_session).get_summary(_NOV_14).school_share_pending is None


def _recorded_at(db_session: Session, sid: int, cycle: int, when: datetime) -> None:
    """Pretend a payment was typed in at ``when``: ``created_at`` is otherwise the server's now."""
    payment = PaymentRepo(db_session).get_by_student_cycle(sid, cycle)
    assert payment is not None
    payment.created_at = when
    db_session.flush()


def test_recorded_today_lists_what_was_typed_in_today_newest_first(db_session: Session) -> None:
    from app.models import ClassLevel

    school_class = ClassService(db_session).create(level=ClassLevel.TC, name="Groupe A")
    amina = (
        StudentService(db_session)
        .enroll(
            first_name="Amina",
            join_date=date(2026, 9, 5),
            custom_price=Decimal("240"),
            class_id=school_class.id,
        )
        .id
    )
    omar = _student(db_session, "Omar", date(2026, 9, 10))
    # Back-dated: September's, paid on 5 September, only typed in today. That is the point.
    _pay(db_session, amina, 0, date(2026, 9, 5), "240")
    _pay(db_session, omar, 2, date(2026, 11, 21), "150")
    # Typed in late yesterday: not today's to check.
    _pay(db_session, omar, 1, date(2026, 10, 10))
    _recorded_at(db_session, amina, 0, datetime(2026, 11, 21, 0, 0, 0))
    _recorded_at(db_session, omar, 2, datetime(2026, 11, 21, 18, 40))
    _recorded_at(db_session, omar, 1, datetime(2026, 11, 20, 23, 59, 59))

    today = DashboardService(db_session).get_summary(date(2026, 11, 21)).recorded_today
    assert [
        (r.name, r.class_label, r.cycle_number, r.for_month, r.paid_date, r.amount) for r in today
    ] == [
        ("Omar", None, 2, "2026-11", date(2026, 11, 21), Decimal("150")),
        ("Amina", "TC — Groupe A", 0, "2026-09", date(2026, 9, 5), Decimal("240")),
    ]
    assert [r.student_id for r in today] == [omar, amina]


def test_recorded_today_reads_the_servers_own_timestamp(db_session: Session) -> None:
    # No timestamp set by hand: the row carries what the database wrote, in its own format.
    sid = _student(db_session, "Now", date(2026, 9, 5))
    _pay(db_session, sid, 0, date(2026, 9, 5))
    payment = PaymentRepo(db_session).get_by_student_cycle(sid, 0)
    assert payment is not None
    db_session.refresh(payment)
    # The database's day rather than date.today(): CURRENT_TIMESTAMP is UTC, the machine may not be.
    recorded_on = payment.created_at.date()

    service = DashboardService(db_session)
    assert [r.name for r in service.get_summary(recorded_on).recorded_today] == ["Now"]
    assert service.get_summary(recorded_on + timedelta(days=1)).recorded_today == []
