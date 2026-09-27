"""The ``User`` model — an account that can sign in to the web app.

Deliberately minimal. There are two users (the two teachers) and accounts are provisioned from
the CLI (``ardoise users add``), so there is no self-service signup, no email, and no
password-reset flow — see ``BACKLOG.md`` §5.

**No ``role`` column.** Both accounts can do everything. Should that ever change, adding one is
``ALTER TABLE user ADD COLUMN role ... DEFAULT ...`` — non-rewriting in SQLite, no backfill — so
carrying a column nothing reads would cost about as much as the migration it saves.

``is_active`` is the column that does earn its place: it switches an account off without deleting
the row, which matters because ``session`` rows point at it. Deactivation is enforced on *every*
request (see ``app.api.deps.require_session``), not just at login, so revoking someone doesn't
leave their existing cookie working for the rest of its 7 days.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base

if TYPE_CHECKING:
    from app.models.session import AuthSession


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint("length(trim(username)) > 0", name="ck_user_username_nonempty"),
        CheckConstraint("length(trim(display_name)) > 0", name="ck_user_display_name_nonempty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Lowercased on the way in (see AuthService) so "Aymen" and "aymen" are the same account and
    # the UNIQUE index actually means what it looks like it means.
    username: Mapped[str] = mapped_column(unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(nullable=False)
    # argon2id, encoded in PHC string format ("$argon2id$v=19$m=...") — the parameters travel
    # with the hash, so raising them later doesn't invalidate existing passwords.
    password_hash: Mapped[str] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # passive_deletes=True: the FK is ON DELETE CASCADE, so deleting a user takes their sessions
    # with it at the database level rather than SQLAlchemy nulling out a NOT NULL column first.
    sessions: Mapped[list["AuthSession"]] = relationship(
        back_populates="user", passive_deletes=True
    )
