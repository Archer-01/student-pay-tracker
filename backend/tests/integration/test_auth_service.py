"""AuthService: accounts, sign-in, session resolution.

Passwords here are deliberately real-ish strings rather than "x" — the service enforces a minimum
length, and a test that quietly used a 1-char password would be testing a different code path.
"""

from datetime import UTC, datetime, timedelta

import pytest
from argon2 import PasswordHasher
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models import AuthSession, User
from app.services.auth_service import AuthService
from app.services.exceptions import (
    DuplicateUserError,
    InvalidCredentialsError,
    InvalidUserError,
    NotAuthenticatedError,
    UserNotFoundError,
)

PASSWORD = "correct-horse"


@pytest.fixture
def service(db_session: Session) -> AuthService:
    return AuthService(db_session)


@pytest.fixture
def user(service: AuthService) -> User:
    return service.create_user(username="aymen", display_name="Aymen", password=PASSWORD)


# --- Accounts --------------------------------------------------------------- #


def test_create_user_hashes_the_password(service: AuthService, user: User) -> None:
    assert user.password_hash != PASSWORD
    assert user.password_hash.startswith("$argon2id$")


def test_create_user_lowercases_the_username(service: AuthService) -> None:
    created = service.create_user(username="  AyMeN  ", display_name="A", password=PASSWORD)
    assert created.username == "aymen"


def test_create_user_rejects_a_duplicate_regardless_of_case(
    service: AuthService, user: User
) -> None:
    with pytest.raises(DuplicateUserError):
        service.create_user(username="AYMEN", display_name="Other", password=PASSWORD)


def test_create_user_rejects_an_empty_username(service: AuthService) -> None:
    with pytest.raises(InvalidUserError) as exc:
        service.create_user(username="   ", display_name="A", password=PASSWORD)
    assert exc.value.code == "username_empty"


def test_create_user_rejects_an_empty_display_name(service: AuthService) -> None:
    with pytest.raises(InvalidUserError) as exc:
        service.create_user(username="a", display_name="  ", password=PASSWORD)
    assert exc.value.code == "display_name_empty"


def test_create_user_rejects_a_short_password(service: AuthService) -> None:
    with pytest.raises(InvalidUserError) as exc:
        service.create_user(username="a", display_name="A", password="short")
    assert exc.value.code == "password_too_short"


def test_list_users_is_ordered_by_username(service: AuthService) -> None:
    service.create_user(username="zaid", display_name="Z", password=PASSWORD)
    service.create_user(username="ayoub", display_name="Y", password=PASSWORD)
    assert [u.username for u in service.list_users()] == ["ayoub", "zaid"]


def test_get_user_is_case_insensitive(service: AuthService, user: User) -> None:
    assert service.get_user("AYMEN").id == user.id


def test_get_user_raises_for_an_unknown_account(service: AuthService) -> None:
    with pytest.raises(UserNotFoundError):
        service.get_user("nobody")


# --- Sign-in ---------------------------------------------------------------- #


def test_login_issues_a_session(service: AuthService, user: User) -> None:
    issued = service.login(username="aymen", password=PASSWORD)
    assert issued.user.id == user.id
    assert issued.token
    assert service.resolve(issued.token).id == user.id


def test_login_accepts_a_differently_cased_username(service: AuthService, user: User) -> None:
    assert service.login(username="AyMeN", password=PASSWORD).user.id == user.id


def test_login_expiry_matches_the_configured_ttl(service: AuthService, user: User) -> None:
    issued = service.login(username="aymen", password=PASSWORD)
    expected = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=settings.session_ttl_days)
    assert abs((issued.expires_at - expected).total_seconds()) < 60


def test_login_rejects_a_wrong_password(service: AuthService, user: User) -> None:
    with pytest.raises(InvalidCredentialsError):
        service.login(username="aymen", password="wrong-password")


def test_login_rejects_an_unknown_username(service: AuthService) -> None:
    with pytest.raises(InvalidCredentialsError):
        service.login(username="nobody", password=PASSWORD)


def test_login_rejects_a_deactivated_account(service: AuthService, user: User) -> None:
    service.set_active("aymen", False)
    with pytest.raises(InvalidCredentialsError):
        service.login(username="aymen", password=PASSWORD)


def test_login_twice_issues_two_distinct_live_sessions(service: AuthService, user: User) -> None:
    """Signing in on a second device must not sign the first one out."""
    first = service.login(username="aymen", password=PASSWORD)
    second = service.login(username="aymen", password=PASSWORD)
    assert first.token != second.token
    assert service.resolve(first.token).id == user.id
    assert service.resolve(second.token).id == user.id


def test_login_purges_that_user_s_expired_sessions(
    service: AuthService, db_session: Session, user: User
) -> None:
    """The table is tidied on the one event that reliably happens — no cron needed."""
    stale = AuthSession(
        token="stale-token",
        user_id=user.id,
        expires_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1),
    )
    db_session.add(stale)
    db_session.commit()

    service.login(username="aymen", password=PASSWORD)
    assert db_session.get(AuthSession, "stale-token") is None


# --- Resolving and revoking ------------------------------------------------- #


@pytest.mark.parametrize("token", [None, "", "not-a-real-token"])
def test_resolve_rejects_a_missing_or_unknown_token(
    service: AuthService, token: str | None
) -> None:
    with pytest.raises(NotAuthenticatedError):
        service.resolve(token)


def test_resolve_rejects_an_expired_session(
    service: AuthService, db_session: Session, user: User
) -> None:
    issued = service.login(username="aymen", password=PASSWORD)
    session_row = db_session.get(AuthSession, issued.token)
    assert session_row is not None
    session_row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    db_session.commit()

    with pytest.raises(NotAuthenticatedError):
        service.resolve(issued.token)


def test_deactivating_an_account_kills_its_live_session_immediately(
    service: AuthService, user: User
) -> None:
    """The point of checking is_active per request rather than only at login."""
    issued = service.login(username="aymen", password=PASSWORD)
    service.set_active("aymen", False)
    with pytest.raises(NotAuthenticatedError):
        service.resolve(issued.token)


def test_reactivating_an_account_does_not_resurrect_old_sessions(
    service: AuthService, user: User
) -> None:
    issued = service.login(username="aymen", password=PASSWORD)
    service.set_active("aymen", False)
    service.set_active("aymen", True)
    with pytest.raises(NotAuthenticatedError):
        service.resolve(issued.token)


def test_set_password_changes_it_and_revokes_every_session(
    service: AuthService, user: User
) -> None:
    issued = service.login(username="aymen", password=PASSWORD)
    service.set_password("aymen", "brand-new-password")

    with pytest.raises(NotAuthenticatedError):
        service.resolve(issued.token)
    with pytest.raises(InvalidCredentialsError):
        service.login(username="aymen", password=PASSWORD)
    assert service.login(username="aymen", password="brand-new-password").user.id == user.id


def test_set_password_rejects_a_short_password(service: AuthService, user: User) -> None:
    with pytest.raises(InvalidUserError) as exc:
        service.set_password("aymen", "short")
    assert exc.value.code == "password_too_short"


def test_set_password_raises_for_an_unknown_account(service: AuthService) -> None:
    with pytest.raises(UserNotFoundError):
        service.set_password("nobody", "a-long-enough-password")


def test_set_active_raises_for_an_unknown_account(service: AuthService) -> None:
    with pytest.raises(UserNotFoundError):
        service.set_active("nobody", False)


def test_logout_drops_only_the_session_used(service: AuthService, user: User) -> None:
    first = service.login(username="aymen", password=PASSWORD)
    second = service.login(username="aymen", password=PASSWORD)

    service.logout(first.token)

    with pytest.raises(NotAuthenticatedError):
        service.resolve(first.token)
    assert service.resolve(second.token).id == user.id


@pytest.mark.parametrize("token", [None, "", "never-existed"])
def test_logout_is_idempotent(service: AuthService, token: str | None) -> None:
    service.logout(token)  # must not raise


# --- Backstops -------------------------------------------------------------- #


def test_resolve_rejects_a_session_whose_user_was_deactivated_out_of_band(
    service: AuthService, db_session: Session, user: User
) -> None:
    """`set_active` revokes sessions itself, so this path is only reachable when `is_active` is
    flipped behind the service's back — a direct DB edit, or the CLI running in another process
    against the same file. That is plausible enough here (the CLI *is* the break-glass tool) to
    keep the per-request check rather than trusting revocation to have happened."""
    issued = service.login(username="aymen", password=PASSWORD)
    db_session.query(User).filter(User.id == user.id).update({"is_active": False})
    db_session.commit()

    with pytest.raises(NotAuthenticatedError):
        service.resolve(issued.token)


def test_login_upgrades_a_hash_written_with_weaker_parameters(
    service: AuthService, db_session: Session, user: User
) -> None:
    """Cost parameters get raised over time; login is the only moment the plaintext is in hand,
    so it is the only place the stored hash can be re-stretched."""
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    db_session.query(User).filter(User.id == user.id).update({"password_hash": weak})
    db_session.commit()

    service.login(username="aymen", password=PASSWORD)

    db_session.refresh(user)
    assert user.password_hash != weak
    assert service.login(username="aymen", password=PASSWORD).user.id == user.id
