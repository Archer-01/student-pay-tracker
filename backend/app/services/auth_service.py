"""Accounts and sign-in: create users, verify passwords, issue and resolve sessions.

The two teachers are provisioned from the CLI (``ardoise users add``); there is no self-service
signup. This service is the single place that knows how a password becomes a session — the API
router and the CLI both go through it, so they can't drift apart.

Sessions are **fixed-expiry, refreshed on login**: ``expires_at`` is stamped once when a session
is created and never slid forward. Logging in again mints a new session rather than extending the
old one, which keeps the read path free of writes — worth having on a single-writer SQLite
database, where every request extending its own session would serialise on the write lock.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import (
    generate_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.core.settings import settings
from app.models import AuthSession, User
from app.services.exceptions import (
    DuplicateUserError,
    InvalidCredentialsError,
    InvalidUserError,
    NotAuthenticatedError,
    UserNotFoundError,
)

# Low enough not to annoy two known users, high enough to rule out "1234". The real protection is
# argon2id's cost, not a composition rule, so there are no character-class requirements.
MIN_PASSWORD_LENGTH: Final = 8


@dataclass(frozen=True)
class IssuedSession:
    """A freshly minted session: the token for the cookie, and when the cookie should lapse."""

    token: str
    expires_at: datetime
    user: User


def _now() -> datetime:
    """Naive UTC. The columns are ``DateTime`` without timezone (SQLite has no native tz type),
    and the rest of the codebase stores naive values — mixing aware and naive here would make
    every ``expires_at`` comparison raise."""
    return datetime.now(UTC).replace(tzinfo=None)


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- Accounts (CLI-facing) --------------------------------------------- #

    def create_user(self, *, username: str, display_name: str, password: str) -> User:
        """Provision an account. Raises on a duplicate username or a too-short password."""
        normalized = self._normalize_username(username)
        display = display_name.strip()
        if not display:
            raise InvalidUserError("display_name_empty")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidUserError("password_too_short", minimum=MIN_PASSWORD_LENGTH)
        if self._find(normalized) is not None:
            raise DuplicateUserError(normalized)

        user = User(
            username=normalized,
            display_name=display,
            password_hash=hash_password(password),
            is_active=True,
        )
        self.session.add(user)
        self.session.commit()
        return user

    def list_users(self) -> list[User]:
        return list(self.session.scalars(select(User).order_by(User.username)))

    def set_password(self, username: str, password: str) -> User:
        """Change an account's password and sign out every browser it was signed in on.

        Revoking on password change is the point: if the password was changed because it leaked,
        leaving the leaked session alive defeats the exercise.
        """
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidUserError("password_too_short", minimum=MIN_PASSWORD_LENGTH)
        user = self.get_user(username)
        user.password_hash = hash_password(password)
        self._revoke_all(user.id)
        self.session.commit()
        return user

    def set_active(self, username: str, is_active: bool) -> User:
        """Enable or disable an account. Disabling also drops its sessions immediately."""
        user = self.get_user(username)
        user.is_active = is_active
        if not is_active:
            self._revoke_all(user.id)
        self.session.commit()
        return user

    def get_user(self, username: str) -> User:
        user = self._find(self._normalize_username(username))
        if user is None:
            raise UserNotFoundError(username)
        return user

    # --- Sign-in / sign-out (API-facing) ----------------------------------- #

    def login(self, *, username: str, password: str) -> IssuedSession:
        """Verify credentials and issue a session. One error for every failure mode."""
        user = self._find(self._normalize_username(username))
        if user is None:
            # Hash anyway so a missing username doesn't return measurably faster than a wrong
            # password, which would make usernames enumerable by timing.
            hash_password(password)
            raise InvalidCredentialsError()
        if not verify_password(user.password_hash, password):
            raise InvalidCredentialsError()
        if not user.is_active:
            raise InvalidCredentialsError()

        # The only event that reliably happens per user, so it's where the table gets tidied —
        # no cron, no background task, and the row count stays bounded by active browsers.
        self._purge_expired(user.id)

        # Upgrade the stored hash if the cost parameters have moved on since it was written.
        # We have the plaintext here and nowhere else, so this is the only chance to do it.
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        issued = AuthSession(
            token=generate_token(),
            user_id=user.id,
            expires_at=_now() + timedelta(days=settings.session_ttl_days),
        )
        self.session.add(issued)
        self.session.commit()
        return IssuedSession(token=issued.token, expires_at=issued.expires_at, user=user)

    def resolve(self, token: str | None) -> User:
        """The user behind a session token. Raises ``NotAuthenticatedError`` for every reason a
        token might not be good: absent, unknown, expired, or belonging to a disabled account."""
        if not token:
            raise NotAuthenticatedError()
        auth_session = self.session.get(AuthSession, token)
        if auth_session is None or auth_session.expires_at <= _now():
            raise NotAuthenticatedError()
        # Checked per request, not just at login, so deactivating an account takes effect now
        # rather than whenever its cookie happens to lapse.
        if not auth_session.user.is_active:
            raise NotAuthenticatedError()
        return auth_session.user

    def logout(self, token: str | None) -> None:
        """Drop one session. Idempotent: signing out twice is not an error."""
        if not token:
            return
        auth_session = self.session.get(AuthSession, token)
        if auth_session is not None:
            self.session.delete(auth_session)
            self.session.commit()

    # --- Internals --------------------------------------------------------- #

    @staticmethod
    def _normalize_username(username: str) -> str:
        normalized = username.strip().lower()
        if not normalized:
            raise InvalidUserError("username_empty")
        return normalized

    def _find(self, username: str) -> User | None:
        return self.session.scalar(select(User).where(User.username == username))

    def _revoke_all(self, user_id: int) -> None:
        self.session.execute(delete(AuthSession).where(AuthSession.user_id == user_id))

    def _purge_expired(self, user_id: int) -> None:
        self.session.execute(
            delete(AuthSession).where(
                AuthSession.user_id == user_id, AuthSession.expires_at <= _now()
            )
        )
