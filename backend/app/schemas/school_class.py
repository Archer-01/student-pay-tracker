"""Request/response schemas for class endpoints (Pydantic v2, separate from the ORM).

Imports flow one way — ``schemas/student.py`` imports :class:`ClassBriefOut` from here, and this
module never imports student schemas. A class's roster is served by the existing
``GET /students?class_id=`` rather than being embedded here, which keeps that direction true and
gives the roster the students endpoint's filters for free.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ClassLevel


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("name must not be blank")
    return value


class ClassCreate(BaseModel):
    level: ClassLevel
    name: str = Field(min_length=1)

    _check_name = field_validator("name")(_not_blank)


class ClassUpdate(BaseModel):
    # extra="forbid" rejects typos with 422 rather than silently ignoring them.
    model_config = ConfigDict(extra="forbid")

    level: ClassLevel | None = None
    name: str | None = Field(default=None, min_length=1)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        return None if value is None else _not_blank(value)


class ClassBriefOut(BaseModel):
    """The nested form carried on a student, for rendering "2BAC — Groupe A" without a lookup."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    level: ClassLevel
    name: str


class ClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: ClassLevel
    name: str
    created_at: datetime


class ClassListItemOut(ClassOut):
    student_count: int
    cumulative_drift: int


class ClassDetailOut(ClassListItemOut):
    as_of: date
