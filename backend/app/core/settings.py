from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": tolerate unknown keys in the environment / .env (e.g. a leftover
    # TEACHER_API_TOKEN) instead of failing to start.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    # Fallback locale when a request doesn't specify one (Accept-Language / ?lang). "en" or "fr".
    default_locale: str = "en"


settings = Settings()
