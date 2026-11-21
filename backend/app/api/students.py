"""Read-only student endpoints."""

from datetime import date
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_locale, require_session
from app.api.pdf_documents import ledger_story, respond
from app.api.pdf_export import slugify_name
from app.core.i18n import translate
from app.models import Student, StudentStatus, User
from app.schemas.enrollment import (
    LeaveRequest,
    PeriodOut,
    ReturnRequest,
    ReturnResultOut,
)
from app.schemas.ledger import LedgerEntryOut, LedgerOut
from app.schemas.override import OverrideCreate, OverrideOut
from app.schemas.payment import PaymentCreate, PaymentOut, PaymentUpdate
from app.schemas.student import (
    StudentCreate,
    StudentDetailOut,
    StudentListItemOut,
    StudentOut,
    StudentUpdate,
)
from app.services.debt_service import DebtService
from app.services.enrollment_service import EnrollmentService
from app.services.ledger_service import LedgerService
from app.services.override_service import OverrideService
from app.services.payment_service import PaymentService
from app.services.pricing_service import PricingService
from app.services.punctuality import average_days_late
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
                price_status=pricing.price_status(student),
                average_days_late=average_days_late(entries, as_of_date),
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
    pricing = PricingService(db)
    return StudentDetailOut(
        **StudentOut.model_validate(student).model_dump(),
        cumulative_drift=summary.cumulative_drift,
        months_overdue=summary.months_overdue,
        amount_owed=summary.amount_owed,
        monthly_price=pricing.price_of(student),
        price_status=pricing.price_status(student),
        next_expected_date=summary.next_expected_date,
        payments_count=summary.payments_count,
        total_paid=summary.total_paid,
        first_payment_date=summary.first_payment_date,
        average_days_late=summary.average_days_late,
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


def _ledger_filename(student: Student) -> str:
    """Download filename for a student's ledger PDF, including a slug of their name when usable."""
    slug = slugify_name(student.full_name)
    stem = f"student-{student.id}-{slug}" if slug else f"student-{student.id}"
    return f"{stem}-ledger.pdf"


@router.get("/{student_id}/ledger.pdf", tags=["reports"])
async def get_ledger_pdf(
    student_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session),
    as_of: date | None = Query(None),
    locale: str = Depends(get_locale),
) -> Response:
    """A student's history on paper, for the teacher or a parent: the student page's status card
    and month tiles, then every payment received."""
    today = date.today()
    as_of_date = as_of or today
    student = StudentService(db).get(student_id)  # 404 if unknown
    ledger = LedgerService(db)
    # Follows the enrolment periods, as the student page does, not `status`.
    periods = EnrollmentService(db).history(student_id)
    leaves = [p.leave_date for p in periods if p.leave_date is not None]
    story = ledger_story(
        student,
        ledger.student_summary(student_id, as_of_date),
        ledger.get_ledger(student_id, as_of_date),
        PricingService(db).price_of(student),
        enrolled=any(p.leave_date is None for p in periods),
        left_on=max(leaves) if leaves else None,
        as_of=as_of_date,
        locale=locale,
        free=PricingService(db).price_status(student) == "free",
    )
    return respond(
        story,
        title=f"{translate('pdf.ledger.title', locale)} · {student.full_name}",
        teacher=user.display_name,
        locale=locale,
        filename=_ledger_filename(student),
        made_on=today,
        as_of=as_of_date,
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
        note=payload.note,
    )
    return StudentOut.model_validate(student)


@router.patch("/{student_id}", response_model=StudentOut)
async def update_student(
    student_id: int, payload: StudentUpdate, db: Session = Depends(get_db)
) -> StudentOut:
    student = StudentService(db).update(student_id, **payload.model_dump(exclude_unset=True))
    return StudentOut.model_validate(student)


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


@router.patch("/{student_id}/payments/{cycle_number}", response_model=PaymentOut, tags=["payments"])
async def update_payment(
    student_id: int, cycle_number: int, payload: PaymentUpdate, db: Session = Depends(get_db)
) -> PaymentOut:
    """Correct a payment's amount or paid date. The month it settles never changes here."""
    payment = PaymentService(db).update_payment(
        student_id=student_id,
        cycle_number=cycle_number,
        amount=payload.amount,
        paid_date=payload.paid_date,
    )
    return PaymentOut.model_validate(payment)


@router.delete(
    "/{student_id}/payments/{cycle_number}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["payments"],
)
async def delete_payment(
    student_id: int, cycle_number: int, db: Session = Depends(get_db)
) -> Response:
    """Remove a payment: the month is owed again. Moving one to another month is this, then a
    new payment for the right month."""
    PaymentService(db).delete_payment(student_id=student_id, cycle_number=cycle_number)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
            amount=owed.amount_owed,
            count=owed.months_owed,
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
