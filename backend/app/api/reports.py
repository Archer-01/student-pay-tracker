"""Monthly and annual report endpoints (JSON + PDF)."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_locale, require_session
from app.api.pdf_documents import annual_story, class_label, monthly_story, respond
from app.core.i18n import translate
from app.core.settings import settings
from app.models import User
from app.schemas.reports import AnnualReportOut, MonthlyReportOut
from app.services.reports_service import ReportsService
from app.services.student_service import StudentService

router = APIRouter(prefix="/reports", tags=["reports"])

_YEAR = Query(..., ge=1, le=9999)
_MONTH = Query(..., ge=1, le=12)


@router.get("/monthly", response_model=MonthlyReportOut)
async def monthly_report(
    year: int = _YEAR, month: int = _MONTH, db: Session = Depends(get_db)
) -> MonthlyReportOut:
    report = ReportsService(db).monthly_report(
        year, month, share_percent=settings.school_share_percent
    )
    return MonthlyReportOut.model_validate(report)


@router.get("/monthly.pdf")
async def monthly_report_pdf(
    year: int = _YEAR,
    month: int = _MONTH,
    db: Session = Depends(get_db),
    user: User = Depends(require_session),
    locale: str = Depends(get_locale),
) -> Response:
    report = ReportsService(db).monthly_report(
        year, month, share_percent=settings.school_share_percent
    )
    # Each student's class, for the grey line under their name; former students included.
    labels = {s.id: class_label(s, locale) for s in StudentService(db).list()}
    return respond(
        monthly_story(report, labels, locale),
        title=f"{translate('pdf.monthly.eyebrow', locale)} · {month:02d}/{year}",
        teacher=user.display_name,
        locale=locale,
        filename=f"monthly-{year}-{month:02d}.pdf",
        made_on=date.today(),
        as_of=report.as_of,
    )


@router.get("/annual", response_model=AnnualReportOut)
async def annual_report(year: int = _YEAR, db: Session = Depends(get_db)) -> AnnualReportOut:
    """What came in over a year, month by month. Every month is present, including empty ones."""
    report = ReportsService(db).annual_report(year, share_percent=settings.school_share_percent)
    return AnnualReportOut.model_validate(report)


@router.get("/annual.pdf")
async def annual_report_pdf(
    year: int = _YEAR,
    db: Session = Depends(get_db),
    user: User = Depends(require_session),
    locale: str = Depends(get_locale),
) -> Response:
    today = date.today()
    report = ReportsService(db).annual_report(year, share_percent=settings.school_share_percent)
    return respond(
        annual_story(report, today, locale),
        title=f"{translate('pdf.annual.eyebrow', locale)} · {year}",
        teacher=user.display_name,
        locale=locale,
        filename=f"annual-{year}.pdf",
        made_on=today,
        # A past year's figures are final at its end; this year's are as of today.
        as_of=min(date(year, 12, 31), today),
    )
