"""Handing the school its share: which months are due, marking one handed over, and undoing it.

The share is derived from what came in (by paid date), as everywhere else; a handover records
what was actually given, so a payment recorded later shows up as a shortfall.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.services.exceptions import HandoverNotFoundError, InvalidHandoverError
from app.services.payment_service import PaymentService
from app.services.school_share_handover_service import SchoolShareHandoverService, ShareMonth
from app.services.student_service import StudentService

QUARTER = Decimal("25")
TODAY = date(2026, 11, 21)


def _amina(db_session: Session) -> int:
    return (
        StudentService(db_session)
        .enroll(first_name="Amina", join_date=date(2026, 9, 5), custom_price=Decimal("240"))
        .id
    )


def _pay(db_session: Session, sid: int, cycle: int, on: date, amount: str = "240") -> None:
    PaymentService(db_session).record_payment(
        student_id=sid, cycle_number=cycle, paid_date=on, amount=Decimal(amount)
    )


def _months(db_session: Session) -> dict[tuple[int, int], ShareMonth]:
    rows = SchoolShareHandoverService(db_session).months(TODAY, QUARTER)
    return {(m.year, m.month): m for m in rows}


def test_months_run_from_the_first_payment_to_now_newest_first(db_session: Session) -> None:
    sid = _amina(db_session)
    _pay(db_session, sid, 0, date(2026, 9, 5))
    _pay(db_session, sid, 1, date(2026, 10, 5))
    rows = SchoolShareHandoverService(db_session).months(TODAY, QUARTER)
    assert [(m.year, m.month, m.due, m.status) for m in rows] == [
        (2026, 11, Decimal("0.00"), "running"),  # this month isn't over
        (2026, 10, Decimal("60.00"), "due"),
        (2026, 9, Decimal("60.00"), "due"),
    ]
    assert rows[1].remaining == Decimal("60.00")


def test_no_payments_or_no_share_means_no_months(db_session: Session) -> None:
    service = SchoolShareHandoverService(db_session)
    assert service.months(TODAY, QUARTER) == []
    sid = _amina(db_session)
    _pay(db_session, sid, 0, date(2026, 9, 5))
    assert service.months(TODAY, Decimal("0")) == []


def test_marking_a_month_records_what_was_handed_over(db_session: Session) -> None:
    sid = _amina(db_session)
    _pay(db_session, sid, 1, date(2026, 10, 5))
    SchoolShareHandoverService(db_session).mark(
        2026, 10, handed_on=date(2026, 11, 3), share_percent=QUARTER, today=TODAY
    )
    october = _months(db_session)[(2026, 10)]
    assert (october.status, october.handed_amount, october.handed_on) == (
        "handed",
        Decimal("60.00"),
        date(2026, 11, 3),
    )
    assert october.remaining == Decimal("0")


def test_a_payment_recorded_later_shows_as_a_shortfall_until_marked_again(
    db_session: Session,
) -> None:
    sid = _amina(db_session)
    _pay(db_session, sid, 1, date(2026, 10, 5))
    service = SchoolShareHandoverService(db_session)
    service.mark(2026, 10, handed_on=date(2026, 11, 3), share_percent=QUARTER, today=TODAY)
    # A second student's October payment, typed in after the handover.
    other = (
        StudentService(db_session)
        .enroll(first_name="Omar", join_date=date(2026, 10, 1), custom_price=Decimal("200"))
        .id
    )
    _pay(db_session, other, 0, date(2026, 10, 20), "200")

    october = _months(db_session)[(2026, 10)]
    assert (october.status, october.due, october.remaining) == (
        "short",
        Decimal("110.00"),
        Decimal("50.00"),
    )
    # Marking again replaces the record with the full share.
    service.mark(2026, 10, handed_on=date(2026, 11, 20), share_percent=QUARTER, today=TODAY)
    october = _months(db_session)[(2026, 10)]
    assert (october.status, october.handed_amount, october.handed_on) == (
        "handed",
        Decimal("110.00"),
        date(2026, 11, 20),
    )


def test_a_mark_can_be_undone(db_session: Session) -> None:
    sid = _amina(db_session)
    _pay(db_session, sid, 1, date(2026, 10, 5))
    service = SchoolShareHandoverService(db_session)
    service.mark(2026, 10, handed_on=date(2026, 11, 3), share_percent=QUARTER, today=TODAY)
    service.unmark(2026, 10)
    assert _months(db_session)[(2026, 10)].status == "due"
    with pytest.raises(HandoverNotFoundError):
        service.unmark(2026, 10)


@pytest.mark.parametrize(
    ("year", "month", "handed_on", "percent", "code"),
    [
        (2026, 11, date(2026, 11, 20), QUARTER, "share_month_not_over"),
        (2026, 10, date(2026, 11, 22), QUARTER, "handover_in_future"),
        (2026, 8, date(2026, 11, 3), QUARTER, "nothing_to_hand_over"),
        (2026, 10, date(2026, 11, 3), Decimal("0"), "school_share_off"),
    ],
)
def test_a_handover_that_makes_no_sense_is_refused(
    db_session: Session, year: int, month: int, handed_on: date, percent: Decimal, code: str
) -> None:
    sid = _amina(db_session)
    _pay(db_session, sid, 1, date(2026, 10, 5))
    _pay(db_session, sid, 2, date(2026, 11, 5))
    with pytest.raises(InvalidHandoverError) as exc:
        SchoolShareHandoverService(db_session).mark(
            year, month, handed_on=handed_on, share_percent=percent, today=TODAY
        )
    assert exc.value.code == code


def test_last_months_share_is_pending_until_handed_over(db_session: Session) -> None:
    sid = _amina(db_session)
    _pay(db_session, sid, 1, date(2026, 10, 5))
    service = SchoolShareHandoverService(db_session)
    pending = service.pending(TODAY, QUARTER)
    assert pending is not None
    assert (pending.year, pending.month, pending.remaining) == (2026, 10, Decimal("60.00"))
    service.mark(2026, 10, handed_on=date(2026, 11, 3), share_percent=QUARTER, today=TODAY)
    assert service.pending(TODAY, QUARTER) is None
    assert service.pending(TODAY, Decimal("0")) is None


def test_a_past_month_with_nothing_collected_has_nothing_to_hand_over(
    db_session: Session,
) -> None:
    sid = _amina(db_session)
    _pay(db_session, sid, 0, date(2026, 9, 5))
    _pay(db_session, sid, 1, date(2026, 11, 2))  # October paid late, in November
    october = _months(db_session)[(2026, 10)]
    assert (october.status, october.due, october.remaining) == (
        "nothing",
        Decimal("0.00"),
        Decimal("0"),
    )


# --------------------------------------------------------------------------- #
# Everything still to hand over, and catching up in one go
# --------------------------------------------------------------------------- #


def _three_months_and_a_short_one(db_session: Session) -> SchoolShareHandoverService:
    """September handed, then short after a late payment; October due; November running."""
    sid = _amina(db_session)
    service = SchoolShareHandoverService(db_session)
    _pay(db_session, sid, 0, date(2026, 9, 5))
    service.mark(2026, 9, handed_on=date(2026, 10, 2), share_percent=QUARTER, today=TODAY)
    _pay(db_session, sid, 1, date(2026, 9, 28), "200")  # paid in September, after the handover
    _pay(db_session, sid, 2, date(2026, 10, 5))
    _pay(db_session, sid, 3, date(2026, 11, 5))
    return service


def test_outstanding_adds_up_every_month_still_to_hand_over(db_session: Session) -> None:
    from app.services.school_share_handover_service import outstanding

    service = _three_months_and_a_short_one(db_session)
    months = service.months(TODAY, QUARTER)
    # September short by 50 (25 % of 200), October due 60, November running (not counted).
    assert outstanding(months) == (Decimal("110.00"), 2)
    assert outstanding([]) == (Decimal("0"), 0)


def test_catching_up_marks_every_due_and_short_month_on_one_day(db_session: Session) -> None:
    service = _three_months_and_a_short_one(db_session)
    marked = service.mark_all(handed_on=date(2026, 11, 20), share_percent=QUARTER, today=TODAY)
    assert marked == 2
    months = {(m.year, m.month): m for m in service.months(TODAY, QUARTER)}
    assert months[(2026, 9)].status == "handed"
    assert months[(2026, 9)].handed_amount == Decimal("110.00")  # the share as it stands now
    assert months[(2026, 10)].status == "handed"
    assert months[(2026, 10)].handed_on == date(2026, 11, 20)
    assert months[(2026, 11)].status == "running"  # this month isn't over: never touched


def test_catching_up_with_nothing_outstanding_marks_nothing(db_session: Session) -> None:
    sid = _amina(db_session)
    _pay(db_session, sid, 0, date(2026, 11, 5))  # only the running month has money
    service = SchoolShareHandoverService(db_session)
    assert service.mark_all(handed_on=TODAY, share_percent=QUARTER, today=TODAY) == 0


@pytest.mark.parametrize(
    ("handed_on", "percent", "code"),
    [
        (date(2026, 11, 22), QUARTER, "handover_in_future"),
        (TODAY, Decimal("0"), "school_share_off"),
    ],
)
def test_catching_up_refuses_what_marking_one_month_refuses(
    db_session: Session, handed_on: date, percent: Decimal, code: str
) -> None:
    service = _three_months_and_a_short_one(db_session)
    with pytest.raises(InvalidHandoverError) as exc:
        service.mark_all(handed_on=handed_on, share_percent=percent, today=TODAY)
    assert exc.value.code == code
