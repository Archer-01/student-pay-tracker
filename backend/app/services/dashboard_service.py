"""Dashboard aggregates — what the teacher needs to act on today.

Three questions, in the order they get asked:

- **What came in?** Payments by *paid date* within ``as_of``'s calendar month.
- **Who owes me?** Students ranked by **money owed**, not by drift. Drift is the product's core
  metric and still travels on every row, but a student with 25 days of drift who is paid up is not
  someone to chase, while one with thirteen unpaid months is.
- **How far along is the month?** This month's dues, at today's prices, against what has been
  paid toward them, and who is due in the coming week. Not the same as "what came in": that
  counts cash by paid date, back payments included, while this counts only this month's fees.
- **What's quietly wrong?** Problems that produce no error and no bill: a student on no pack is
  charged nothing, month after month, and nothing else in the app says so.
- **Did I type that right?** The payments recorded today, so a typo is caught the same day.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Payment, Student, StudentStatus
from app.repos import PaymentRepo, StudentRepo
from app.services.debt_service import DebtService
from app.services.enrollment_service import EnrollmentService
from app.services.ledger_service import LedgerService
from app.services.pricing_service import PriceStatus, PricingService
from app.services.schedule import add_months
from app.services.school_share import ShareSplit, split
from app.services.school_share_handover_service import SchoolShareHandoverService, ShareMonth


@dataclass(frozen=True)
class StudentDigest:
    """One student as the dashboard needs them: who, where, and how far behind."""

    student_id: int
    name: str
    class_label: str | None
    monthly_price: Decimal
    price_status: PriceStatus
    cumulative_drift: int
    months_overdue: int
    amount_owed: Decimal


@dataclass(frozen=True)
class MonthProgress:
    """This month's fees: what they come to (what was paid for a paid month, the price for an
    unpaid one), and what has been paid toward them."""

    expected: Decimal
    settled: Decimal
    students_expected: int
    # Students with every one of this month's dues paid (usually one each).
    students_settled: int


@dataclass(frozen=True)
class DueSoon:
    """A payment that falls due in the coming week and isn't paid yet."""

    student_id: int
    name: str
    class_label: str | None
    due_date: date
    amount: Decimal


# How far ahead "this week" looks: today and the six days after it.
DUE_SOON_DAYS = 7

DueSoonList = list[DueSoon]


@dataclass(frozen=True)
class RecordedToday:
    """A payment typed in today, whatever day it was paid and whichever month it settles."""

    student_id: int
    name: str
    class_label: str | None
    cycle_number: int
    # The month it pays for, "YYYY-MM": the month its due date falls in.
    for_month: str
    paid_date: date
    amount: Decimal


RecordedTodayList = list[RecordedToday]


@dataclass(frozen=True)
class DashboardSummary:
    as_of: date
    total_collected_this_month: Decimal
    share_this_month: ShareSplit
    total_outstanding: Decimal
    active_students: int
    # Ranked by money owed, then by drift — the order you would work down the list in.
    top_debtors: list[StudentDigest]
    # Money owed by students who have already left. Separate from `total_outstanding`, which
    # covers the ones still attending: chasing the two groups is a different conversation.
    leavers_with_debt: int
    owed_by_leavers: Decimal
    # --- Silent problems, each empty in a healthy database -------------------
    # Attending but priced at nothing: no pack and no agreed price, so they are invoiced zero
    # every month and appear in no arrears figure.
    unbilled_students: list[StudentDigest]
    # Marked as having left, yet still holding an open attendance period — the state migration
    # 0006 leaves behind, because it refuses to invent a departure date. Their billing keeps
    # running until a real leave is recorded.
    missing_leave_date: list[StudentDigest]
    this_month: MonthProgress
    # Soonest first.
    due_this_week: DueSoonList
    # Last month's share for the school, while any of it is still to hand over.
    school_share_pending: ShareMonth | None
    # Newest first.
    recorded_today: RecordedTodayList


class DashboardService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.students = StudentRepo(session)
        self.payments = PaymentRepo(session)
        self.ledger = LedgerService(session)
        self.pricing = PricingService(session)
        self.debts = DebtService(session)
        self.enrollment = EnrollmentService(session)

    def get_summary(
        self, as_of: date, top_n: int = 5, *, share_percent: Decimal = Decimal("0")
    ) -> DashboardSummary:
        month_start = as_of.replace(day=1)
        next_month_start = add_months(month_start, 1)
        collected = sum(
            (p.amount for p in self.payments.list_paid_between(month_start, next_month_start)),
            Decimal("0"),
        )

        outstanding = Decimal("0")
        debtors: list[StudentDigest] = []
        unbilled: list[StudentDigest] = []
        active = self.students.list(status=StudentStatus.ACTIVE)
        for student in active:
            digest = self._digest(student, as_of)
            outstanding += digest.amount_owed
            if digest.price_status == "unset":
                # Free on purpose is not a problem to flag (decision 0011); a missing price is.
                unbilled.append(digest)
            elif digest.amount_owed > 0 or digest.cumulative_drift > 0:
                debtors.append(digest)

        # Money first, drift as the tie-break: two students owing the same are ordered by how
        # long they have been making a habit of it.
        debtors.sort(key=lambda d: (d.amount_owed, d.cumulative_drift), reverse=True)

        leavers = self.debts.leavers_with_debt()
        this_month, due_soon = self._month_and_week(active, as_of)
        return DashboardSummary(
            as_of=as_of,
            total_collected_this_month=collected,
            share_this_month=split(collected, share_percent),
            total_outstanding=outstanding,
            active_students=len(active),
            top_debtors=debtors[:top_n],
            leavers_with_debt=len(leavers),
            owed_by_leavers=sum((s.amount_owed for s in leavers), Decimal("0")),
            unbilled_students=unbilled,
            missing_leave_date=[
                self._digest(student, as_of)
                for student in self.students.list(status=StudentStatus.INACTIVE)
                if self.enrollment.is_attending(student.id)
            ],
            this_month=this_month,
            due_this_week=due_soon,
            school_share_pending=SchoolShareHandoverService(self.session).pending(
                as_of, share_percent
            ),
            recorded_today=self._recorded_on(as_of),
        )

    def _recorded_on(self, day: date) -> RecordedTodayList:
        """Payments typed in on ``day``, by when they were recorded, not when they were paid: a
        back payment entered today is exactly the one worth a second look.

        By ``date()`` of the stored timestamp rather than a datetime range, since SQLite's
        ``CURRENT_TIMESTAMP`` has no fraction and would sort below a bound that has one.
        """
        stmt = (
            select(Payment)
            .where(func.date(Payment.created_at) == day.isoformat())
            .order_by(Payment.created_at.desc(), Payment.id.desc())
        )
        return [
            RecordedToday(
                student_id=p.student_id,
                name=p.student.full_name,
                class_label=_class_label(p.student),
                cycle_number=p.cycle_number,
                for_month=p.expected_due_date.strftime("%Y-%m"),
                paid_date=p.paid_date,
                amount=p.amount,
            )
            for p in self.session.scalars(stmt)
        ]

    def _month_and_week(
        self, students: list[Student], as_of: date
    ) -> tuple[MonthProgress, DueSoonList]:
        """This month's dues and the coming week's, from each billable student's schedule.

        One ledger pass per student, up to whichever is later of the month's end and a week
        ahead: the schedule there is override-aware, includes dues later this month, and marks
        months the student was away (suspended, so not owed).
        """
        month_start = as_of.replace(day=1)
        month_end = add_months(month_start, 1) - timedelta(days=1)
        week_end = as_of + timedelta(days=DUE_SOON_DAYS - 1)
        horizon = max(month_end, week_end)

        expected = settled = Decimal("0")
        students_expected = students_settled = 0
        due_soon: DueSoonList = []
        for student in students:
            if not self.pricing.billable(student):
                continue
            price = self.pricing.price_of(student)
            owed = [e for e in self.ledger.get_ledger(student.id, horizon) if not e.suspended]

            this_month = [e for e in owed if month_start <= e.expected_due_date <= month_end]
            if this_month:
                paid = [e for e in this_month if e.paid_date is not None]
                paid_total = sum((e.amount or Decimal("0") for e in paid), Decimal("0"))
                # A paid month counts what was paid, not today's price: several students pay
                # below their listed price, and they are settled all the same.
                expected += paid_total + price * (len(this_month) - len(paid))
                settled += paid_total
                students_expected += 1
                if len(paid) == len(this_month):
                    students_settled += 1

            due_soon += [
                DueSoon(
                    student_id=student.id,
                    name=student.full_name,
                    class_label=_class_label(student),
                    due_date=e.expected_due_date,
                    amount=price,
                )
                for e in owed
                if e.paid_date is None and as_of <= e.expected_due_date <= week_end
            ]

        due_soon.sort(key=lambda d: (d.due_date, d.name))
        progress = MonthProgress(expected, settled, students_expected, students_settled)
        return progress, due_soon

    def _digest(self, student: Student, as_of: date) -> StudentDigest:
        summary = self.ledger.student_summary(student.id, as_of)
        return StudentDigest(
            student_id=student.id,
            name=student.full_name,
            class_label=_class_label(student),
            monthly_price=self.pricing.price_of(student),
            price_status=self.pricing.price_status(student),
            cumulative_drift=summary.cumulative_drift,
            months_overdue=summary.months_overdue,
            amount_owed=summary.amount_owed,
        )


def _class_label(student: Student) -> str | None:
    if student.school_class is None:
        return None
    return f"{student.school_class.level.value} — {student.school_class.name}"
