"""Read-only student endpoints."""

import re
import unicodedata
from datetime import date
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_locale
from app.api.pdf_export import render_table_pdf
from app.core.db import get_db
from app.core.i18n import translate
from app.models import Student, StudentStatus
from app.schemas.ledger import LedgerEntryOut, LedgerOut
from app.schemas.override import OverrideCreate, OverrideOut
from app.schemas.payment import PaymentCreate, PaymentOut
from app.schemas.student import (
    DriftOut,
    StudentCreate,
    StudentDetailOut,
    StudentListItemOut,
    StudentOut,
    StudentUpdate,
)
from app.services.ledger_service import LedgerEntry, LedgerService
from app.services.override_service import OverrideService
from app.services.payment_service import PaymentService
from app.services.student_service import StudentService

router = APIRouter(prefix="/students", tags=["students"])


class StudentSort(StrEnum):
    drift_desc = "drift_desc"


@router.get("", response_model=list[StudentListItemOut])
async def list_students(
    db: Session = Depends(get_db),
    status: StudentStatus | None = Query(None),
    sort: StudentSort | None = Query(None),
    as_of: date | None = Query(None),
) -> list[StudentListItemOut]:
    as_of_date = as_of or date.today()
    ledger = LedgerService(db)
    items: list[StudentListItemOut] = []
    for student in StudentService(db).list(status=status):
        # One ledger pass yields both drift (running total) and arrears (unpaid due cycles).
        entries = ledger.get_ledger(student.id, as_of_date)
        drift = entries[-1].cumulative_drift if entries else 0
        months_overdue = 0 if student.fee == 0 else sum(1 for e in entries if e.paid_date is None)
        items.append(
            StudentListItemOut(
                **StudentOut.model_validate(student).model_dump(),
                cumulative_drift=drift,
                months_overdue=months_overdue,
            )
        )
    if sort is StudentSort.drift_desc:
        items.sort(key=lambda item: item.cumulative_drift, reverse=True)
    return items


@router.get("/{student_id}", response_model=StudentDetailOut)
async def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    as_of: date | None = Query(None),
) -> StudentDetailOut:
    as_of_date = as_of or date.today()
    student = StudentService(db).get(student_id)
    summary = LedgerService(db).student_summary(student_id, as_of_date)
    return StudentDetailOut(
        **StudentOut.model_validate(student).model_dump(),
        cumulative_drift=summary.cumulative_drift,
        months_overdue=summary.months_overdue,
        next_expected_date=summary.next_expected_date,
        payments_count=summary.payments_count,
        total_paid=summary.total_paid,
        as_of=as_of_date,
    )


@router.get("/{student_id}/ledger", response_model=LedgerOut)
async def get_ledger(
    student_id: int,
    db: Session = Depends(get_db),
    as_of: date | None = Query(None),
) -> LedgerOut:
    as_of_date = as_of or date.today()
    entries = LedgerService(db).get_ledger(student_id, as_of_date)
    total = entries[-1].cumulative_drift if entries else 0
    return LedgerOut(
        student_id=student_id,
        as_of=as_of_date,
        cumulative_drift=total,
        entries=[LedgerEntryOut.model_validate(e) for e in entries],
    )


@router.get("/{student_id}/drift", response_model=DriftOut)
async def get_drift(
    student_id: int,
    db: Session = Depends(get_db),
    as_of: date | None = Query(None),
) -> DriftOut:
    as_of_date = as_of or date.today()
    drift = LedgerService(db).cumulative_drift(student_id, as_of_date)
    return DriftOut(student_id=student_id, as_of=as_of_date, cumulative_drift=drift)


def _ledger_row_status(entry: LedgerEntry, locale: str) -> str:
    if entry.paid_date is None:
        return translate("csv.ledger.status.unpaid", locale)
    if entry.days_late is not None and entry.days_late > 0:
        return translate("csv.ledger.status.days_late", locale, days=entry.days_late)
    return translate("csv.ledger.status.on_time", locale)


def _ledger_subtitle(student: Student, locale: str) -> str:
    """The student's name, plus a localized phone line when a phone number is on file."""
    if student.phone:
        return f"{student.name}\n{translate('pdf.ledger.phone', locale, phone=student.phone)}"
    return student.name


def _slugify_name(name: str) -> str:
    """An ASCII, filename-safe slug of a name (accents folded, non-alphanumerics hyphenated).

    Returns "" for names that carry no ASCII letters/digits (e.g. Arabic script) — the caller
    then falls back to an id-only filename rather than emitting an empty or non-ASCII one.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", folded).strip("-").lower()


def _ledger_filename(student: Student) -> str:
    """Download filename for a student's ledger PDF, including a slug of their name when usable."""
    slug = _slugify_name(student.name)
    stem = f"student-{student.id}-{slug}" if slug else f"student-{student.id}"
    return f"{stem}-ledger.pdf"


def _ledger_export(entries: list[LedgerEntry], locale: str) -> tuple[list[str], list[list[str]]]:
    """Localized (header, rows) for the ledger export — cells are strings, ready to render."""
    header = [
        translate(f"csv.ledger.{col}", locale)
        for col in (
            "cycle",
            "due_date",
            "paid_date",
            "days_late",
            "amount",
            "cumulative_drift",
            "status",
        )
    ]
    rows = [
        [
            str(e.cycle_number),
            e.expected_due_date.isoformat(),
            e.paid_date.isoformat() if e.paid_date else "",
            str(e.days_late) if e.days_late is not None else "",
            f"{e.amount:.2f}" if e.amount is not None else "",
            str(e.cumulative_drift),
            _ledger_row_status(e, locale),
        ]
        for e in entries
    ]
    return header, rows


@router.get("/{student_id}/ledger.pdf", tags=["reports"])
async def get_ledger_pdf(
    student_id: int,
    db: Session = Depends(get_db),
    as_of: date | None = Query(None),
    locale: str = Depends(get_locale),
) -> Response:
    as_of_date = as_of or date.today()
    student = StudentService(db).get(student_id)  # 404 if unknown
    entries = LedgerService(db).get_ledger(student_id, as_of_date)
    header, rows = _ledger_export(entries, locale)
    title = translate("pdf.ledger.title", locale)
    subtitle = _ledger_subtitle(student, locale)
    return render_table_pdf(
        title, header, rows, _ledger_filename(student), subtitle=subtitle
    )


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
async def create_student(payload: StudentCreate, db: Session = Depends(get_db)) -> StudentOut:
    student = StudentService(db).enroll(
        name=payload.name,
        phone=payload.phone,
        join_date=payload.join_date,
        fee=payload.fee,
        status=payload.status,
    )
    return StudentOut.model_validate(student)


@router.patch("/{student_id}", response_model=StudentOut)
async def update_student(
    student_id: int, payload: StudentUpdate, db: Session = Depends(get_db)
) -> StudentOut:
    student = StudentService(db).update(student_id, **payload.model_dump(exclude_unset=True))
    return StudentOut.model_validate(student)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(student_id: int, db: Session = Depends(get_db)) -> Response:
    """Hard-delete a student and cascade to their payments and overrides (admin/dev only)."""
    StudentService(db).delete(student_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{student_id}/payments",
    response_model=PaymentOut,
    status_code=status.HTTP_201_CREATED,
    tags=["payments"],
)
async def record_payment(
    student_id: int, payload: PaymentCreate, db: Session = Depends(get_db)
) -> PaymentOut:
    payments = PaymentService(db)
    if payload.for_month is not None:
        year, month = map(int, payload.for_month.split("-"))
        try:
            cycle_number = payments.cycle_for_month(student_id, year, month)
        except ValueError as exc:  # month precedes the schedule
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        assert payload.cycle_number is not None  # guaranteed by the schema validator
        cycle_number = payload.cycle_number
    payment = payments.record_payment(
        student_id=student_id,
        cycle_number=cycle_number,
        paid_date=payload.paid_date,
        amount=payload.amount,
    )
    return PaymentOut.model_validate(payment)


@router.post(
    "/{student_id}/overrides",
    response_model=OverrideOut,
    status_code=status.HTTP_201_CREATED,
    tags=["overrides"],
)
async def create_override(
    student_id: int, payload: OverrideCreate, db: Session = Depends(get_db)
) -> OverrideOut:
    override = OverrideService(db).create_override(
        student_id=student_id, new_due_date=payload.new_due_date, reason=payload.reason
    )
    return OverrideOut.model_validate(override)
