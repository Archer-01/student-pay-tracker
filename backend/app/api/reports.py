"""Monthly report endpoints (JSON + PDF)."""

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_locale
from app.api.pdf_export import render_table_pdf
from app.core.db import get_db
from app.core.i18n import translate
from app.schemas.reports import MonthlyReportOut
from app.services.reports_service import MonthlyReport, ReportsService

router = APIRouter(prefix="/reports", tags=["reports"])

_YEAR = Query(..., ge=1, le=9999)
_MONTH = Query(..., ge=1, le=12)

_MONTHLY_COLUMNS = (
    "student_id",
    "name",
    "status",
    "fee",
    "collected",
    "cumulative_drift",
    "outstanding",
)


def _monthly_export(report: MonthlyReport, locale: str) -> tuple[list[str], list[list[str]]]:
    """Localized (header, rows) for the monthly report export — cells are strings."""
    header = [translate(f"csv.monthly.{col}", locale) for col in _MONTHLY_COLUMNS]
    rows = [
        [
            str(row.student_id),
            row.name,
            translate(f"status.{row.status.value}", locale),
            f"{row.fee:.2f}",
            f"{row.collected:.2f}",
            str(row.cumulative_drift),
            f"{row.outstanding:.2f}",
        ]
        for row in report.rows
    ]
    return header, rows


@router.get("/monthly", response_model=MonthlyReportOut)
async def monthly_report(
    year: int = _YEAR, month: int = _MONTH, db: Session = Depends(get_db)
) -> MonthlyReportOut:
    report = ReportsService(db).monthly_report(year, month)
    return MonthlyReportOut.model_validate(report)


@router.get("/monthly.pdf")
async def monthly_report_pdf(
    year: int = _YEAR,
    month: int = _MONTH,
    db: Session = Depends(get_db),
    locale: str = Depends(get_locale),
) -> Response:
    report = ReportsService(db).monthly_report(year, month)
    header, rows = _monthly_export(report, locale)
    title = translate("pdf.monthly.title", locale, year=year, month=month)
    return render_table_pdf(title, header, rows, f"monthly-{year}-{month:02d}.pdf")
