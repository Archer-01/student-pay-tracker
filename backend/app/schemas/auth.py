"""Request/response schemas for sign-in.

``UserOut`` deliberately has no ``password_hash`` field — the hash must never leave the process,
and a Pydantic schema that simply doesn't declare it is a stronger guarantee than remembering to
strip it at each call site.
"""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    # No max_length on the password and no character-class rules: argon2id does the work, and a
    # length cap would only stop people using a passphrase.
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
