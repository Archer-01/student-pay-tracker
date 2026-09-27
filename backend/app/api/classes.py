"""Class endpoints — roster grouping for students. Never touches drift, the anchor, or payments.

A class's roster is deliberately *not* embedded in the detail response: it is served by the
existing ``GET /students?class_id=``, which already returns drift and arrears per student and
supports the status/sort filters. One representation of a student list, not two.
"""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_locale
from app.api.pdf_export import Stat, render_report_pdf, slugify_name
from app.core.i18n import translate
from app.models import ClassLevel, SchoolClass
from app.schemas.school_class import (
    ClassCreate,
    ClassDetailOut,
    ClassListItemOut,
    ClassOut,
    ClassUpdate,
)
from app.services.class_service import ClassService, RosterRows

router = APIRouter(prefix="/classes", tags=["classes"])

_ROSTER_COLUMNS = (
    "student_id",
    "name",
    "phone",
    "status",
    "price",
    "cumulative_drift",
    "months_overdue",
    "amount_owed",
)


def _totals(rows: RosterRows) -> tuple[int, int]:
    """(student_count, class-wide cumulative drift) for a class's roster rows."""
    return len(rows), sum(row.cumulative_drift for row in rows)


@router.get("", response_model=list[ClassListItemOut])
async def list_classes(
    db: Session = Depends(get_db),
    level: ClassLevel | None = Query(None),
    as_of: date | None = Query(None),
) -> list[ClassListItemOut]:
    as_of_date = as_of or date.today()
    service = ClassService(db)
    items: list[ClassListItemOut] = []
    for school_class in service.list(level=level):
        count, drift = _totals(service.roster(school_class.id, as_of_date))
        items.append(
            ClassListItemOut(
                **ClassOut.model_validate(school_class).model_dump(),
                student_count=count,
                cumulative_drift=drift,
            )
        )
    return items


@router.post("", response_model=ClassOut, status_code=status.HTTP_201_CREATED)
async def create_class(payload: ClassCreate, db: Session = Depends(get_db)) -> ClassOut:
    school_class = ClassService(db).create(level=payload.level, name=payload.name)
    return ClassOut.model_validate(school_class)


@router.get("/{class_id}", response_model=ClassDetailOut)
async def get_class(
    class_id: int,
    db: Session = Depends(get_db),
    as_of: date | None = Query(None),
) -> ClassDetailOut:
    as_of_date = as_of or date.today()
    service = ClassService(db)
    school_class = service.get(class_id)
    count, drift = _totals(service.roster(class_id, as_of_date))
    return ClassDetailOut(
        **ClassOut.model_validate(school_class).model_dump(),
        student_count=count,
        cumulative_drift=drift,
        as_of=as_of_date,
    )


@router.patch("/{class_id}", response_model=ClassOut)
async def update_class(
    class_id: int, payload: ClassUpdate, db: Session = Depends(get_db)
) -> ClassOut:
    school_class = ClassService(db).update(class_id, **payload.model_dump(exclude_unset=True))
    return ClassOut.model_validate(school_class)


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(class_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete an empty class. A class that still has students is refused with 409."""
    ClassService(db).delete(class_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _roster_export(rows: RosterRows, locale: str) -> tuple[list[str], list[list[str]]]:
    """Localized (header, rows) for the roster export — cells are strings, ready to render."""
    header = [translate(f"csv.roster.{col}", locale) for col in _ROSTER_COLUMNS]
    body = [
        [
            str(row.student.id),
            row.student.full_name,
            row.student.phone or "",
            translate(f"status.{row.student.status.value}", locale),
            f"{row.monthly_price:.2f}",
            str(row.cumulative_drift),
            str(row.months_overdue),
            f"{row.amount_owed:.2f}",
        ]
        for row in rows
    ]
    return header, body


def _roster_filename(school_class: SchoolClass) -> str:
    """Download filename for a class roster, e.g. ``2bac-groupe-a-roster.pdf``."""
    slug = slugify_name(f"{school_class.level.value} {school_class.name}")
    stem = slug or f"class-{school_class.id}"
    return f"{stem}-roster.pdf"


def _roster_stats(rows: RosterRows, locale: str) -> list[Stat]:
    """Class-level totals, so the sheet answers "how is this class doing" at a glance."""
    owed = sum((row.amount_owed for row in rows), Decimal("0"))
    behind = sum(1 for row in rows if row.months_overdue > 0)
    return [
        Stat(translate("pdf.stat.students", locale), str(len(rows))),
        Stat(translate("csv.roster.months_overdue", locale), str(behind)),
        Stat(translate("pdf.stat.outstanding", locale), f"{owed:.2f}"),
        Stat(
            translate("pdf.stat.drift", locale),
            translate(
                "pdf.value.days", locale, days=sum(row.cumulative_drift for row in rows)
            ),
        ),
    ]


@router.get("/{class_id}/roster.pdf", tags=["reports"])
async def get_roster_pdf(
    class_id: int,
    db: Session = Depends(get_db),
    as_of: date | None = Query(None),
    locale: str = Depends(get_locale),
) -> Response:
    as_of_date = as_of or date.today()
    service = ClassService(db)
    school_class = service.get(class_id)  # 404 if unknown
    roster = service.roster(class_id, as_of_date)
    header, rows = _roster_export(roster, locale)
    return render_report_pdf(
        title=translate("pdf.roster.title", locale),
        subtitle=f"{school_class.level.value} — {school_class.name}",
        stats=_roster_stats(roster, locale),
        header=header,
        rows=rows,
        filename=_roster_filename(school_class),
        footer=translate(
            "pdf.footer", locale, generated=date.today().isoformat(), as_of=as_of_date.isoformat()
        ),
        empty_message=translate("pdf.roster.empty", locale),
    )
