"""The dev seed dataset (`app.core.seed`): counts and the intended feature spread."""

from datetime import date

from sqlalchemy.orm import Session

from app.core.seed import SEED_STUDENTS, seed_dummy_data
from app.models import StudentStatus
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
