from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from app.core.offsite_backup import BackupConfig


class Settings(BaseSettings):
    # extra="ignore": tolerate unknown keys in the environment / .env (a variable from an older
    # version, another tool's) instead of failing to start.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    # How long a signed-in browser stays signed in. Fixed, not sliding: the expiry is stamped
    # once at login and never moved, so everyone re-authenticates at least this often. 90 days:
    # each teacher signs in on his own phone, and a password asked for every week was a chore
    # that protected nothing extra. Also the cookie's max-age (app/api/auth.py).
    session_ttl_days: int = 90
    # The session cookie's Secure flag. Must be False for local dev (the Vite dev server is
    # plain http://localhost, and a Secure cookie is silently dropped there — login would
    # appear to succeed and then never stick). Keep it True everywhere else.
    cookie_secure: bool = True
    # Fallback locale when a request doesn't specify one (Accept-Language / ?lang). "en" or "fr".
    default_locale: str = "en"
    # The school owner's percentage of every payment the teacher receives. Bilan and Accueil show
    # it next to what came in, with what's left for the teacher. 0 hides the split entirely.
    # One value for every account and every month: changing it recalculates past months too.
    school_share_percent: Decimal = Field(default=Decimal("25"), ge=0, le=100)
    # The nightly off-site copy (decision 0012, docs/backups.md). All three or nothing: without
    # them the app runs with no off-site backup, and /health says "off".
    backup_url: str | None = None  # the Apps Script web app
    backup_secret: str | None = None  # also set in the script's properties
    backup_public_key: str | None = None  # "age1…"; its private half stays with the developer
    backup_hour: int = Field(default=3, ge=0, le=23)  # Morocco time

    def backup_config(self) -> "BackupConfig | None":
        from app.core.offsite_backup import BackupConfig

        if not (self.backup_url and self.backup_secret and self.backup_public_key):
            return None
        return BackupConfig(
            url=self.backup_url,
            secret=self.backup_secret,
            public_key=self.backup_public_key,
            hour=self.backup_hour,
        )


settings = Settings()
