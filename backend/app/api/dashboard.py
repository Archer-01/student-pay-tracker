"""Read-only dashboard endpoint."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.dashboard import DashboardSummaryOut
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryOut)
async def get_summary(
    db: Session = Depends(get_db),
    as_of: date | None = Query(None),
    limit: int = Query(5, ge=1, le=100),
) -> DashboardSummaryOut:
    as_of_date = as_of or date.today()
    summary = DashboardService(db).get_summary(as_of_date, top_n=limit)
    return DashboardSummaryOut.model_validate(summary)
