"""Settings read from environment variables (and `.env` when present).

One typed object instead of scattered `os.getenv` calls: a missing or malformed
value fails at startup, not in the middle of a request.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str
    # Separate database for pytest, so tests can wipe it freely.
    test_database_url: str | None = None
    jwt_secret_key: str = "dev-only-not-secret"
    jwt_expire_minutes: int = 600
    # Comma-separated in the environment, e.g. "http://localhost:5173,https://x.onrender.com".
    cors_origins: str = "http://localhost:5173"
    seed_demo_password: str = "demo-change-me"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Build settings once per process and reuse them."""
    return Settings()
