"""Response schemas for the monthly report."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import StudentStatus


class MonthlyReportRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: int
    name: str
    status: StudentStatus
    fee: Decimal
    collected: Decimal
    cumulative_drift: int
    outstanding: Decimal


class MonthlyReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    as_of: date
    total_collected: Decimal
    total_outstanding: Decimal
    rows: list[MonthlyReportRowOut]
