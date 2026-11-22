"""Handing the school its share: the months due, marking one handed over (or undoing it), and
catching up on all of them at once."""

from datetime import date

from fastapi import APIRouter, Depends, Path, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.settings import settings
from app.schemas.school_share import HandoverIn, SchoolShareOut, ShareMonthOut
from app.services.school_share_handover_service import SchoolShareHandoverService, outstanding

router = APIRouter(prefix="/school-share", tags=["reports"])

_YEAR = Path(..., ge=2000, le=9999)
_MONTH = Path(..., ge=1, le=12)


@router.get("", response_model=SchoolShareOut)
async def list_months(db: Session = Depends(get_db)) -> SchoolShareOut:
    percent = settings.school_share_percent
    months = SchoolShareHandoverService(db).months(date.today(), percent)
    total, count = outstanding(months)
    return SchoolShareOut(
        percent=percent,
        months=[ShareMonthOut.model_validate(m) for m in months],
        outstanding=total,
        outstanding_months=count,
    )


@router.post("/hand-over-all", response_model=SchoolShareOut)
async def hand_over_all(payload: HandoverIn, db: Session = Depends(get_db)) -> SchoolShareOut:
    """Catch up: mark every ended month still to hand over as handed over on one day."""
    SchoolShareHandoverService(db).mark_all(
        handed_on=payload.handed_on,
        share_percent=settings.school_share_percent,
        today=date.today(),
    )
    return await list_months(db)


@router.put("/{year}/{month}", response_model=SchoolShareOut)
async def mark_handed_over(
    payload: HandoverIn,
    year: int = _YEAR,
    month: int = _MONTH,
    db: Session = Depends(get_db),
) -> SchoolShareOut:
    """Record that the month's share was handed over; marking again replaces the record."""
    SchoolShareHandoverService(db).mark(
        year,
        month,
        handed_on=payload.handed_on,
        share_percent=settings.school_share_percent,
        today=date.today(),
    )
    return await list_months(db)


@router.delete("/{year}/{month}", status_code=status.HTTP_204_NO_CONTENT)
async def unmark_handed_over(
    year: int = _YEAR, month: int = _MONTH, db: Session = Depends(get_db)
) -> Response:
    SchoolShareHandoverService(db).unmark(year, month)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
