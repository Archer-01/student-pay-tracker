from decimal import Decimal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": tolerate unknown keys in the environment / .env (e.g. a leftover
    # TEACHER_API_TOKEN) instead of failing to start.
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


settings = Settings()
