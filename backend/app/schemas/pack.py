"""Request/response schemas for pack, offering and assignment endpoints (Pydantic v2)."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class OfferingCreate(BaseModel):
    """Create every level-variant of an offering at once — one grid row.

    Prices are keyed by level; a level omitted here simply isn't offered, which is legal (the
    grid may legitimately have empty cells).
    """

    name: str = Field(min_length=1)
    subjects: list[str] = Field(min_length=1)
    prices: dict[ClassLevel, Money]

    @field_validator("prices")
    @classmethod
    def _prices_non_negative(cls, value: dict[ClassLevel, Decimal]) -> dict[ClassLevel, Decimal]:
        if not value:
            raise ValueError("at least one level price is required")
        if any(price < 0 for price in value.values()):
            raise ValueError("prices must not be negative")
        return value


class OfferingUpdate(BaseModel):
    """Rename an offering and/or change its subjects — applied to every level-variant."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    subjects: list[str] | None = Field(default=None, min_length=1)


class PackUpdate(BaseModel):
    """Edit one grid cell. Name/subjects belong to the offering, so they're not accepted here."""

    model_config = ConfigDict(extra="forbid")

    price: Money | None = Field(default=None, ge=0)
    is_active: bool | None = None


class GridCellOut(BaseModel):
    """One (offering, level) cell. ``pack_id`` is null when the offering isn't sold at a level."""

    level: ClassLevel
    pack_id: int | None
    price: Decimal | None
    is_active: bool | None
    student_count: int


class GridRowOut(BaseModel):
    name: str
    subjects: list[str]
    cells: list[GridCellOut]


class PackGridOut(BaseModel):
    """The offerings x levels price matrix — what the packs screen renders."""

    levels: list[ClassLevel]
    rows: list[GridRowOut]
