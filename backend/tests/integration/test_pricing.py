"""Pricing: one number per student, and where it comes from.

    effective price = student.custom_price if set, else the pack's price, else nothing

The trade this model makes is explicit and tested below: prices are **not** historical. Changing a
pack's price, or moving a student to another pack, changes what they owe for months they have not
yet paid. Recorded payments keep their own frozen amount, so money already taken never moves.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models import ClassLevel
from app.services.class_service import ClassService
from app.services.exceptions import InvalidPackError, PackNotFoundError
from app.services.ledger_service import LedgerService
from app.services.pack_service import PackService
from app.services.payment_service import PaymentService
from app.services.pricing_service import PricingService
from app.services.student_service import StudentService

_JOIN = date(2023, 3, 5)
_AS_OF = date(2023, 6, 30)  # cycles 0..3 are due by here


def _pack(session: Session, name: str = "Maths seul", price: str = "150"):
    return PackService(session).create(
        name=name, level=ClassLevel.BAC2, price=Decimal(price), subjects=["Maths"]
    )


def _student(session: Session, **kw: object):
    return StudentService(session).enroll(
        first_name="Amina", phone=None, join_date=_JOIN, **kw
    )


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def test_price_comes_from_the_pack(db_session: Session) -> None:
    pack = _pack(db_session, price="150")
    student = _student(db_session, pack_id=pack.id)
    assert PricingService(db_session).price_of(student) == Decimal("150")


def test_a_custom_price_overrides_the_pack(db_session: Session) -> None:
    pack = _pack(db_session, price="150")
    student = _student(db_session, pack_id=pack.id, custom_price=Decimal("90"))
    assert PricingService(db_session).price_of(student) == Decimal("90")


def test_a_student_with_no_pack_has_no_price(db_session: Session) -> None:
    student = _student(db_session)
    assert PricingService(db_session).price_of(student) == Decimal("0")


def test_a_custom_price_works_without_a_pack(db_session: Session) -> None:
    """How students migrated from the old `fee` column arrive: a price, no pack yet."""
    student = _student(db_session, custom_price=Decimal("300"))
    assert PricingService(db_session).price_of(student) == Decimal("300")


def test_clearing_the_custom_price_returns_them_to_the_pack_price(db_session: Session) -> None:
    pack = _pack(db_session, price="150")
    student = _student(db_session, pack_id=pack.id, custom_price=Decimal("90"))
    StudentService(db_session).update(student.id, custom_price=None)
    assert PricingService(db_session).price_of(student) == Decimal("150")


# --------------------------------------------------------------------------- #
# Arrears
# --------------------------------------------------------------------------- #


def test_amount_owed_is_unpaid_months_times_the_price(db_session: Session) -> None:
    pack = _pack(db_session, price="150")
    student = _student(db_session, pack_id=pack.id)
    summary = LedgerService(db_session).student_summary(student.id, _AS_OF)
    assert summary.months_overdue == 4
    assert summary.amount_owed == Decimal("600")


def test_a_student_with_no_price_owes_nothing(db_session: Session) -> None:
    student = _student(db_session)
    summary = LedgerService(db_session).student_summary(student.id, _AS_OF)
    assert summary.months_overdue == 0
    assert summary.amount_owed == Decimal("0")


def test_a_free_pack_owes_nothing(db_session: Session) -> None:
    pack = _pack(db_session, name="Bourse", price="0")
    student = _student(db_session, pack_id=pack.id)
    summary = LedgerService(db_session).student_summary(student.id, _AS_OF)
    assert summary.months_overdue == 0
    assert summary.amount_owed == Decimal("0")


def test_paid_cycles_are_not_owed(db_session: Session) -> None:
    pack = _pack(db_session, price="150")
    student = _student(db_session, pack_id=pack.id)
    PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=0, paid_date=_JOIN, amount=Decimal("150")
    )
    summary = LedgerService(db_session).student_summary(student.id, _AS_OF)
    assert summary.months_overdue == 3
    assert summary.amount_owed == Decimal("450")


# --------------------------------------------------------------------------- #
# The accepted trade: pricing is not historical
# --------------------------------------------------------------------------- #


def test_a_pack_price_change_reprices_unpaid_months(db_session: Session) -> None:
    """Deliberate. Prices are current, not historical — see the module docstring."""
    pack = _pack(db_session, price="150")
    student = _student(db_session, pack_id=pack.id)
    assert LedgerService(db_session).student_summary(student.id, _AS_OF).amount_owed == Decimal(
        "600"
    )
    PackService(db_session).update(pack.id, price=Decimal("200"))
    assert LedgerService(db_session).student_summary(student.id, _AS_OF).amount_owed == Decimal(
        "800"
    )


def test_a_price_change_never_touches_recorded_payments(db_session: Session) -> None:
    """The other half of the trade: money already taken is frozen and must not move."""
    pack = _pack(db_session, price="150")
    student = _student(db_session, pack_id=pack.id)
    payment = PaymentService(db_session).record_payment(
        student_id=student.id, cycle_number=0, paid_date=_JOIN, amount=Decimal("150")
    )
    PackService(db_session).update(pack.id, price=Decimal("999"))
    db_session.refresh(payment)
    assert payment.amount == Decimal("150")


def test_a_custom_price_shields_a_student_from_a_pack_price_change(db_session: Session) -> None:
    pack = _pack(db_session, price="150")
    student = _student(db_session, pack_id=pack.id, custom_price=Decimal("90"))
    PackService(db_session).update(pack.id, price=Decimal("500"))
    assert PricingService(db_session).price_of(student) == Decimal("90")


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def test_enrolling_onto_an_unknown_pack_raises(db_session: Session) -> None:
    with pytest.raises(PackNotFoundError):
        _student(db_session, pack_id=999)


def test_enrolling_onto_a_retired_pack_raises(db_session: Session) -> None:
    pack = _pack(db_session)
    PackService(db_session).update(pack.id, is_active=False)
    with pytest.raises(InvalidPackError) as exc:
        _student(db_session, pack_id=pack.id)
    assert exc.value.code == "pack_inactive"


def test_a_negative_custom_price_is_rejected(db_session: Session) -> None:
    pack = _pack(db_session)
    with pytest.raises(InvalidPackError) as exc:
        _student(db_session, pack_id=pack.id, custom_price=Decimal("-1"))
    assert exc.value.code == "custom_price_negative"


def test_moving_to_an_unknown_pack_raises(db_session: Session) -> None:
    student = _student(db_session)
    with pytest.raises(PackNotFoundError):
        StudentService(db_session).update(student.id, pack_id=999)


def test_a_student_can_be_taken_off_their_pack(db_session: Session) -> None:
    pack = _pack(db_session)
    student = _student(db_session, pack_id=pack.id)
    StudentService(db_session).update(student.id, pack_id=None)
    assert student.pack_id is None
    assert PricingService(db_session).price_of(student) == Decimal("0")


# --------------------------------------------------------------------------- #
# Level mismatch — advisory, never a block
# --------------------------------------------------------------------------- #


def test_a_level_mismatch_is_reported_but_allowed(db_session: Session) -> None:
    school_class = ClassService(db_session).create(level=ClassLevel.AC1, name="Groupe A")
    pack = _pack(db_session)  # 2BAC
    student = _student(db_session, class_id=school_class.id, pack_id=pack.id)
    assert student.pack_id == pack.id  # succeeded
    assert PricingService(db_session).level_mismatch(student, pack) == (
        ClassLevel.AC1,
        ClassLevel.BAC2,
    )


def test_no_mismatch_when_levels_agree_or_there_is_no_class(db_session: Session) -> None:
    pricing = PricingService(db_session)
    pack = _pack(db_session)
    assert pricing.level_mismatch(_student(db_session), pack) is None

    school_class = ClassService(db_session).create(level=ClassLevel.BAC2, name="Groupe A")
    matched = StudentService(db_session).enroll(
        first_name="B", phone=None, join_date=_JOIN, class_id=school_class.id, pack_id=pack.id
    )
    assert pricing.level_mismatch(matched, pack) is None
