"""ORM models. Importing this package registers every table on ``Base.metadata``.

Alembic's ``env.py`` imports ``Base`` from here so autogenerate sees all tables.
"""

from app.core.db import Base
from app.models.anchor_override import AnchorOverride
from app.models.debt import DebtWriteoff
from app.models.enrollment import EnrollmentPeriod
from app.models.pack import Pack, Subject, pack_subject
from app.models.payment import Payment
from app.models.school_class import ClassLevel, SchoolClass
from app.models.session import AuthSession
from app.models.student import Student, StudentStatus
from app.models.user import User

__all__ = [
    "AnchorOverride",
    "AuthSession",
    "Base",
    "ClassLevel",
    "DebtWriteoff",
    "EnrollmentPeriod",
    "Pack",
    "Payment",
    "SchoolClass",
    "Student",
    "StudentStatus",
    "Subject",
    "User",
    "pack_subject",
]
