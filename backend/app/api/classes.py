"""Class endpoints — roster grouping for students. Never touches drift, the anchor, or payments.

A class's roster is deliberately *not* embedded in the detail response: it is served by the
existing ``GET /students?class_id=``, which already returns drift and arrears per student and
supports the status/sort filters. One representation of a student list, not two.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_locale, require_session
from app.api.pdf_documents import respond, roster_story
from app.api.pdf_export import slugify_name
from app.core.i18n import translate
from app.models import ClassLevel, SchoolClass, User
from app.schemas.school_class import (
    ClassCreate,
    ClassDetailOut,
    ClassListItemOut,
    ClassOut,
    ClassUpdate,
)
from app.services.class_service import ClassService, RosterRows

router = APIRouter(prefix="/classes", tags=["classes"])

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


def _roster_filename(school_class: SchoolClass) -> str:
    """Download filename for a class roster, e.g. ``2bac-groupe-a-roster.pdf``."""
    slug = slugify_name(f"{school_class.level.value} {school_class.name}")
    stem = slug or f"class-{school_class.id}"
    return f"{stem}-roster.pdf"


@router.get("/{class_id}/roster.pdf", tags=["reports"])
async def get_roster_pdf(
    class_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_session),
    as_of: date | None = Query(None),
    locale: str = Depends(get_locale),
) -> Response:
    today = date.today()
    as_of_date = as_of or today
    service = ClassService(db)
    school_class = service.get(class_id)  # 404 if unknown
    title = f"{school_class.level.value} — {school_class.name}"
    return respond(
        roster_story(title, service.roster(class_id, as_of_date), locale),
        title=f"{translate('pdf.roster.title', locale)} · {title}",
        teacher=user.display_name,
        locale=locale,
        filename=_roster_filename(school_class),
        made_on=today,
        as_of=as_of_date,
    )
