"""The ``AuthSession`` model — one signed-in browser.

Named ``AuthSession`` (table ``auth_session``), not ``Session``, for the same reason
``SchoolClass`` isn't ``Class``: every module in this codebase does ``from sqlalchemy.orm import
Session``, and a second ``Session`` in scope would be a standing invitation to a confusing bug.

Server-side sessions rather than a JWT: they can be revoked instantly (delete the row), and the
token is an opaque random string that means nothing outside this table. The cookie carrying it is
HttpOnly, so page scripts can't read it.

**Fixed expiry, refreshed on login** — ``expires_at`` is stamped once at creation and never slid
forward, so a signed-in browser re-authenticates every 7 days regardless of activity. Logging in
again simply creates a new row. That also means there is no per-request write on the hot path,
which matters for a single-writer SQLite database.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.user import User


class AuthSession(Base):
    __tablename__ = "auth_session"

    # The opaque cookie value itself, not a surrogate integer: the lookup is by token, and a
    # guessable sequential id would be a poor thing to hand out as a credential.
    token: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="sessions")
