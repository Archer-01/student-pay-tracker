"""Response schemas for the monthly and annual reports."""

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


class ShareOut(BaseModel):
    """What came in, split between the school owner and the teacher (see services/school_share)."""

    model_config = ConfigDict(from_attributes=True)

    percent: Decimal
    school: Decimal
    teacher: Decimal


class MonthlyReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    month: int
    as_of: date
    total_collected: Decimal
    total_outstanding: Decimal
    rows: list[MonthlyReportRowOut]
    share: ShareOut


class AnnualMonthOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: int
    collected: Decimal
    payments_count: int
    share: ShareOut


class AnnualReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    year: int
    months: list[AnnualMonthOut]
    total_collected: Decimal
    payments_count: int
    share: ShareOut
