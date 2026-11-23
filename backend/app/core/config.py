"""Settings read from environment variables (and `.env` when present).

One typed object instead of scattered `os.getenv` calls: a missing or malformed
value fails at startup, not in the middle of a request.
"""

from functools import lru_cache

from pydantic import field_validator
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
    # Built React files. Set in the production image; absent in dev, so nothing is mounted.
    static_dir: str | None = None

    @field_validator("database_url", "test_database_url")
    @classmethod
    def use_psycopg3_driver(cls, url: str | None) -> str | None:
        """Hosts (e.g. Neon) hand out postgres:// or postgresql:// URLs. SQLAlchemy would then
        pick psycopg2, which we don't install, so point them at psycopg 3 explicitly."""
        if url is None:
            return None
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Build settings once per process and reuse them."""
    return Settings()
