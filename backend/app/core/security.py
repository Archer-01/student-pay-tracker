"""Password hashing and session-token generation.

argon2id with the ``argon2-cffi`` defaults, which are the OWASP-recommended parameters and are
tuned to take a noticeable fraction of a second — that slowness is the point.

Kept in ``core`` rather than the service layer because it is infrastructure, not domain logic:
nothing here knows what a user is.
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Stateless and thread-safe; built once so the parameter choice lives in exactly one place.
_hasher = PasswordHasher()

# 32 bytes of urandom, URL-safe base64 -> ~43 chars. Far beyond guessing range, and safe to put
# in a cookie without escaping.
_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    """Hash a plaintext password into a PHC string ("$argon2id$v=19$m=...")."""
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a password against a stored hash. False on any mismatch or malformed hash.

    Swallows ``InvalidHashError`` deliberately: a corrupt or hand-edited row should fail the login
    like a wrong password rather than 500 the endpoint.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when a stored hash predates the current cost parameters and should be upgraded."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def generate_token() -> str:
    """A fresh opaque session token."""
    return secrets.token_urlsafe(_TOKEN_BYTES)
