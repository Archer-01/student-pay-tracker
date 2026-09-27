from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": tolerate unknown keys in the environment / .env (e.g. a leftover
    # TEACHER_API_TOKEN) instead of failing to start.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    # How long a signed-in browser stays signed in. Fixed, not sliding: the expiry is stamped
    # once at login and never moved, so everyone re-authenticates at least this often.
    session_ttl_days: int = 7
    # The session cookie's Secure flag. Must be False for local dev (the Vite dev server is
    # plain http://localhost, and a Secure cookie is silently dropped there — login would
    # appear to succeed and then never stick). Keep it True everywhere else.
    cookie_secure: bool = True
    # Fallback locale when a request doesn't specify one (Accept-Language / ?lang). "en" or "fr".
    default_locale: str = "en"


settings = Settings()
