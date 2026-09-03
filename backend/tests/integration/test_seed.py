"""The dev seed dataset (`app.core.seed`): counts and the intended feature spread."""

from datetime import date

from sqlalchemy.orm import Session

from app.core.seed import SEED_CLASSES, SEED_STUDENTS, seed_dummy_data
from app.models import StudentStatus
from app.services.class_service import ClassService
from app.services.ledger_service import LedgerService
from app.services.student_service import StudentService

_AS_OF = date(2026, 8, 6)


def test_seed_creates_expected_counts(db_session: Session) -> None:
    expected_payments = sum(len(s.payments) for s in SEED_STUDENTS)
    expected_overrides = sum(len(s.overrides) for s in SEED_STUDENTS)

    summary = seed_dummy_data(db_session)

    assert summary.students == len(SEED_STUDENTS)
    assert summary.payments == expected_payments
    assert summary.overrides == expected_overrides
    assert len(StudentService(db_session).list()) == len(SEED_STUDENTS)


def test_seed_spread_covers_every_feature(db_session: Session) -> None:
    seed_dummy_data(db_session)
    students = StudentService(db_session).list()
    ledger = LedgerService(db_session)

    # An inactive student and a phone-less student are present (report filter / PDF name-only).
    assert any(s.status is StudentStatus.INACTIVE for s in students)
    assert any(s.phone is None for s in students)
    # At least one student has accumulated real drift, and at least one is fully on time.
    drifts = [ledger.cumulative_drift(s.id, _AS_OF) for s in students]
    assert max(drifts) > 0
    assert min(drifts) == 0


def test_seed_is_idempotent_per_call_but_appends(db_session: Session) -> None:
    # The function itself only appends; the double-seed guard lives in the CLI command.
    seed_dummy_data(db_session)
    seed_dummy_data(db_session)
    assert len(StudentService(db_session).list()) == 2 * len(SEED_STUDENTS)
    # Classes are reused, not duplicated — (level, name) is unique.
    assert len(ClassService(db_session).list()) == len(SEED_CLASSES)


def test_seed_creates_the_full_pack_grid(db_session: Session) -> None:
    from app.core.seed import SEED_OFFERINGS
    from app.services.pack_service import PackService

    seed_dummy_data(db_session)
    packs = PackService(db_session).list()
    expected = sum(len(prices) for _, _, prices in SEED_OFFERINGS)
    assert len(packs) == expected == 24


def test_seeded_offerings_share_one_subject_set_across_levels(db_session: Session) -> None:
    from app.services.pack_service import PackService

    seed_dummy_data(db_session)
    by_name: dict[str, set[tuple[str, ...]]] = {}
    for pack in PackService(db_session).list():
        by_name.setdefault(pack.name, set()).add(tuple(sorted(s.name for s in pack.subjects)))
    assert all(len(variants) == 1 for variants in by_name.values())


def test_seed_covers_the_pricing_cases_worth_seeing(db_session: Session) -> None:
    """An agreed price below the pack's, and a student with no pack (so not yet billed)."""
    from decimal import Decimal

    from app.services.pricing_service import PricingService
    from app.services.student_service import StudentService

    seed_dummy_data(db_session)
    pricing = PricingService(db_session)
    by_name = {s.full_name: s for s in StudentService(db_session).list()}

    discounted = by_name["Sara Idrissi"]
    assert discounted.custom_price is not None
    assert discounted.pack is not None
    assert discounted.custom_price < discounted.pack.price
    assert discounted.price_note
    assert pricing.price_of(discounted) == discounted.custom_price

    on_pack_price = by_name["Omar Tazi"]
    assert on_pack_price.custom_price is None
    assert pricing.price_of(on_pack_price) == on_pack_price.pack.price

    unbilled = by_name["Mehdi Alaoui"]
    assert unbilled.pack is None
    assert pricing.price_of(unbilled) == Decimal("0")


def test_reseeding_reuses_the_pack_grid(db_session: Session) -> None:
    from app.services.pack_service import PackService

    seed_dummy_data(db_session)
    seed_dummy_data(db_session)
    assert len(PackService(db_session).list()) == 24
