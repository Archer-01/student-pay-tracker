"""Monthly report endpoints (JSON + PDF)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_locale
from app.api.pdf_export import Stat, render_report_pdf
from app.core.i18n import translate
from app.schemas.reports import AnnualReportOut, MonthlyReportOut
from app.services.reports_service import AnnualReport, MonthlyReport, ReportsService

router = APIRouter(prefix="/reports", tags=["reports"])

_YEAR = Query(..., ge=1, le=9999)
_MONTH = Query(..., ge=1, le=12)

_MONTHLY_COLUMNS = (
    "student_id",
    "name",
    "status",
    "price",
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
    behind = sum(1 for row in report.rows if row.outstanding > 0)
    return render_report_pdf(
        title=translate("pdf.monthly.title", locale, year=year, month=month),
        stats=[
            Stat(translate("pdf.stat.students", locale), str(len(report.rows))),
            Stat(translate("pdf.stat.collected", locale), f"{report.total_collected:.2f}"),
            Stat(translate("pdf.stat.outstanding", locale), f"{report.total_outstanding:.2f}"),
            Stat(translate("csv.roster.months_overdue", locale), str(behind)),
        ],
        header=header,
        rows=rows,
        filename=f"monthly-{year}-{month:02d}.pdf",
        footer=translate(
            "pdf.footer",
            locale,
            generated=date.today().isoformat(),
            as_of=report.as_of.isoformat(),
        ),
        empty_message=translate("pdf.monthly.empty", locale),
    )


_ANNUAL_COLUMNS = ("month", "collected", "payments")


def _annual_export(report: AnnualReport, locale: str) -> tuple[list[str], list[list[str]]]:
    """Localized (header, rows) for the annual report — one row per month, empty ones included."""
    header = [translate(f"csv.annual.{col}", locale) for col in _ANNUAL_COLUMNS]
    rows = [
        [
            translate(f"month.{row.month}", locale),
            f"{row.collected:.2f}",
            str(row.payments_count),
        ]
        for row in report.months
    ]
    return header, rows


def _annual_stats(report: AnnualReport, locale: str) -> list[Stat]:
    earning = [row for row in report.months if row.collected > 0]
    best = max(report.months, key=lambda row: row.collected) if earning else None
    # Averaged over the months that actually earned, not over twelve — a year that only ran from
    # September would otherwise look like it took a third of what it did.
    average = report.total_collected / len(earning) if earning else Decimal("0")
    return [
        Stat(translate("pdf.stat.collected", locale), f"{report.total_collected:.2f}"),
        Stat(translate("csv.annual.payments", locale), str(report.payments_count)),
        Stat(translate("pdf.stat.monthly_average", locale), f"{average:.2f}"),
        Stat(
            translate("pdf.stat.best_month", locale),
            translate(f"month.{best.month}", locale)
            if best
            else translate("pdf.value.none", locale),
        ),
    ]


@router.get("/annual", response_model=AnnualReportOut)
async def annual_report(year: int = _YEAR, db: Session = Depends(get_db)) -> AnnualReportOut:
    """What came in over a year, month by month. Every month is present, including empty ones."""
    return AnnualReportOut.model_validate(ReportsService(db).annual_report(year))


@router.get("/annual.pdf")
async def annual_report_pdf(
    year: int = _YEAR,
    db: Session = Depends(get_db),
    locale: str = Depends(get_locale),
) -> Response:
    report = ReportsService(db).annual_report(year)
    header, rows = _annual_export(report, locale)
    return render_report_pdf(
        title=translate("pdf.annual.title", locale, year=year),
        stats=_annual_stats(report, locale),
        header=header,
        # An empty year still lists its months; the message covers the no-payments case.
        rows=rows if report.payments_count else [],
        filename=f"annual-{year}.pdf",
        footer=translate(
            "pdf.footer",
            locale,
            generated=date.today().isoformat(),
            as_of=date(year, 12, 31).isoformat(),
        ),
        empty_message=translate("pdf.annual.empty", locale),
    )
