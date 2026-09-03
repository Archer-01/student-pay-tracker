"""Read-only student endpoints."""

from datetime import date
from decimal import Decimal
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_locale
from app.api.pdf_export import Stat, render_report_pdf, slugify_name
from app.core.db import get_db
from app.core.i18n import translate
from app.models import Student, StudentStatus
from app.schemas.enrollment import (
    LeaveRequest,
    PeriodAmend,
    PeriodOut,
    ReturnRequest,
    ReturnResultOut,
)
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
from app.services.debt_service import DebtService
from app.services.enrollment_service import EnrollmentService
from app.services.ledger_service import LedgerEntry, LedgerService, StudentSummary
from app.services.override_service import OverrideService
from app.services.payment_service import PaymentService
from app.services.pricing_service import PricingService
from app.services.student_service import StudentService

router = APIRouter(prefix="/students", tags=["students"])


class StudentSort(StrEnum):
    drift_desc = "drift_desc"


@router.get("", response_model=list[StudentListItemOut])
async def list_students(
    db: Session = Depends(get_db),
    status: StudentStatus | None = Query(None),
    sort: StudentSort | None = Query(None),
    class_id: int | None = Query(None, description="Only students in this class."),
    q: str | None = Query(None, description="Search first or last name."),
    as_of: date | None = Query(None),
) -> list[StudentListItemOut]:
    as_of_date = as_of or date.today()
    ledger = LedgerService(db)
    pricing = PricingService(db)
    items: list[StudentListItemOut] = []
    for student in StudentService(db).list(status=status, class_id=class_id, query=q):
        # One ledger pass yields drift, arrears and the money owed — all priced per cycle by
        # PricingService, so the "what does a month cost" rule lives in exactly one place.
        entries = ledger.get_ledger(student.id, as_of_date)
        unpaid_due = ledger.unpaid_due_dates(student, entries)
        items.append(
            StudentListItemOut(
                **StudentOut.model_validate(student).model_dump(),
                cumulative_drift=entries[-1].cumulative_drift if entries else 0,
                months_overdue=len(unpaid_due),
                amount_owed=pricing.amount_for_cycles(student, unpaid_due),
                monthly_price=pricing.price_of(student),
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
        amount_owed=summary.amount_owed,
        monthly_price=PricingService(db).price_of(student),
        next_expected_date=summary.next_expected_date,
        payments_count=summary.payments_count,
        total_paid=summary.total_paid,
        first_payment_date=summary.first_payment_date,
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
    # "Away" before "Unpaid": a month the student wasn't enrolled for is not a debt.
    if entry.suspended:
        return translate("csv.ledger.status.away", locale)
    if entry.paid_date is None:
        return translate("csv.ledger.status.unpaid", locale)
    if entry.days_late is not None and entry.days_late > 0:
        return translate("csv.ledger.status.days_late", locale, days=entry.days_late)
    return translate("csv.ledger.status.on_time", locale)


def _fmt_date(value: date | None, locale: str) -> str:
    return value.isoformat() if value else translate("pdf.value.none", locale)


def _class_label(student: Student, locale: str) -> str:
    if student.school_class is None:
        return translate("pdf.value.unassigned", locale)
    return f"{student.school_class.level.value} — {student.school_class.name}"


def _pack_label(student: Student, locale: str) -> str:
    """The pack name, plus its level only when that differs from the student's class.

    Printing the level unconditionally reads as a stutter — "2BAC — Groupe A · Maths seul · 2BAC" —
    since the class already says it. When they disagree, though, that is exactly what a reader
    needs to see.
    """
    if student.pack is None:
        return translate("pdf.value.no_pack", locale)
    same_level = (
        student.school_class is not None
        and student.school_class.level is student.pack.level
    )
    return student.pack.name if same_level else f"{student.pack.name} · {student.pack.level.value}"


def _ledger_facts(
    student: Student, summary: StudentSummary, locale: str
) -> list[tuple[str, str]]:
    """The secondary detail block: everything about the student that isn't a headline figure."""
    yes_no = translate("pdf.value.yes" if student.is_repeating else "pdf.value.no", locale)
    facts = [
        (translate("pdf.field.phone", locale),
         student.phone or translate("pdf.value.none", locale)),
        (
            translate("pdf.field.status", locale),
            translate(f"status.{student.status.value}", locale),
        ),
        (translate("pdf.field.repeating", locale), yes_no),
        (translate("pdf.field.join_date", locale), _fmt_date(student.join_date, locale)),
        (translate("pdf.field.first_payment", locale),
         _fmt_date(summary.first_payment_date, locale)),
    ]
    # Only shown when there is an arrangement — otherwise it's noise on every export.
    if student.custom_price is not None:
        note = student.price_note or translate("pdf.value.none", locale)
        facts.append((translate("pdf.field.price_note", locale), note))
    return facts


def _ledger_stats(summary: StudentSummary, monthly_price: Decimal, locale: str) -> list[Stat]:
    return [
        Stat(translate("pdf.stat.monthly_price", locale), f"{monthly_price:.2f}"),
        Stat(translate("pdf.stat.total_paid", locale), f"{summary.total_paid:.2f}"),
        Stat(translate("pdf.stat.months_overdue", locale), str(summary.months_overdue)),
        Stat(translate("pdf.stat.amount_owed", locale), f"{summary.amount_owed:.2f}"),
        Stat(
            translate("pdf.stat.drift", locale),
            translate("pdf.value.days", locale, days=summary.cumulative_drift),
        ),
    ]


def _ledger_filename(student: Student) -> str:
    """Download filename for a student's ledger PDF, including a slug of their name when usable."""
    slug = slugify_name(student.full_name)
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
    ledger = LedgerService(db)
    summary = ledger.student_summary(student_id, as_of_date)
    header, rows = _ledger_export(ledger.get_ledger(student_id, as_of_date), locale)
    price = PricingService(db).price_of(student)
    return render_report_pdf(
        title=translate("pdf.ledger.title", locale),
        subtitle=student.full_name,
        meta=f"{_class_label(student, locale)} · {_pack_label(student, locale)}",
        stats=_ledger_stats(summary, price, locale),
        facts=_ledger_facts(student, summary, locale),
        header=header,
        rows=rows,
        filename=_ledger_filename(student),
        footer=translate(
            "pdf.footer", locale, generated=date.today().isoformat(), as_of=as_of_date.isoformat()
        ),
        empty_message=translate("pdf.ledger.empty", locale),
    )


@router.post("", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
async def create_student(payload: StudentCreate, db: Session = Depends(get_db)) -> StudentOut:
    student = StudentService(db).enroll(
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        is_repeating=payload.is_repeating,
        join_date=payload.join_date,
        status=payload.status,
        class_id=payload.class_id,
        pack_id=payload.pack_id,
        custom_price=payload.custom_price,
        price_note=payload.price_note,
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


@router.get("/{student_id}/periods", response_model=list[PeriodOut], tags=["enrollment"])
async def list_periods(student_id: int, db: Session = Depends(get_db)) -> list[PeriodOut]:
    """A student's attendance history, oldest first."""
    return [PeriodOut.model_validate(p) for p in EnrollmentService(db).history(student_id)]


@router.post("/{student_id}/leave", response_model=PeriodOut, tags=["enrollment"])
async def record_leave(
    student_id: int, payload: LeaveRequest, db: Session = Depends(get_db)
) -> PeriodOut:
    """Record a departure. Months after it stop being owed; drift already accrued is untouched."""
    period = EnrollmentService(db).leave(
        student_id, leave_date=payload.leave_date, reason=payload.reason
    )
    return PeriodOut.model_validate(period)


@router.post("/{student_id}/return", response_model=ReturnResultOut, tags=["enrollment"])
async def record_return(
    student_id: int,
    payload: ReturnRequest,
    db: Session = Depends(get_db),
    locale: str = Depends(get_locale),
) -> ReturnResultOut:
    """Record a return, opening a new period.

    Deliberately **not** blocked by an outstanding balance: the teacher decides whether to
    re-admit someone who owes money (backlog §2.3). ``join_date`` is never moved, so a returning
    student keeps the drift and the debt they left with.
    """
    # What they owed *before* returning: reopening a period un-suspends future months, so the
    # figure has to be read first or it would already have moved.
    owed = DebtService(db).status(student_id)
    period = EnrollmentService(db).return_(student_id, entry_date=payload.entry_date)
    warning = (
        translate(
            "warning.returning_with_debt",
            locale,
            amount=f"{owed.amount_owed:.2f}",
            months=owed.months_owed,
        )
        if owed.left_with_debt
        else None
    )
    return ReturnResultOut(
        **PeriodOut.model_validate(period).model_dump(),
        amount_owed=owed.amount_owed,
        months_owed=owed.months_owed,
        debt_warning=warning,
    )


@router.patch(
    "/{student_id}/periods/{period_id}", response_model=PeriodOut, tags=["enrollment"]
)
async def amend_period(
    student_id: int,
    period_id: int,
    payload: PeriodAmend,
    db: Session = Depends(get_db),
) -> PeriodOut:
    """Correct a mistyped date. Every ordering rule is re-checked afterwards."""
    period = EnrollmentService(db).amend(
        student_id, period_id, **payload.model_dump(exclude_unset=True)
    )
    return PeriodOut.model_validate(period)
