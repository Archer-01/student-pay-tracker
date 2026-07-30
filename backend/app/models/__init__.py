"""ORM models. Importing this package registers every table on ``Base.metadata``.

Alembic's ``env.py`` imports ``Base`` from here so autogenerate sees all tables.
"""

from app.core.db import Base
from app.models.anchor_override import AnchorOverride
from app.models.payment import Payment
from app.models.student import Student, StudentStatus

__all__ = ["AnchorOverride", "Base", "Payment", "Student", "StudentStatus"]
