"""Request/response schemas for pack, offering and assignment endpoints (Pydantic v2)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models import ClassLevel
from app.schemas.money import Money


class PackBriefOut(BaseModel):
    """The nested form carried on a student, for rendering "Maths seul · 2BAC" without a lookup."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    level: ClassLevel
    price: Decimal


class PackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    level: ClassLevel
    price: Decimal
    is_active: bool
    created_at: datetime


class PackDetailOut(PackOut):
    subjects: list[str]
    student_count: int


class PackCreate(BaseModel):
    """Create a single pack (one offering at one level)."""

    name: str = Field(min_length=1)
    level: ClassLevel
    price: Money = Field(ge=0)
    subjects: list[str] = Field(min_length=1)


class PackUpdate(BaseModel):
    """Edit one pack: its name, level (only while no student is on it), subjects, price, and
    whether it's still offered. Only the fields sent are changed."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    level: ClassLevel | None = None
    subjects: list[str] | None = Field(default=None, min_length=1)
    price: Money | None = Field(default=None, ge=0)
    is_active: bool | None = None
