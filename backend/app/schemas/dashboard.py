"""Response schemas for the dashboard endpoint."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class LatecomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: int
    name: str
    cumulative_drift: int


class DashboardSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: date
    total_collected_this_month: Decimal
    total_outstanding: Decimal
    top_latecomers: list[LatecomerOut]
