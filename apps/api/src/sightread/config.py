"""Environment settings. `.env.example` at the repo root is the authoritative variable list."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Only ever used when APP_ENV=local and SECRET_KEY is unset, so `uv run uvicorn` works
# without a .env file. Production refuses to start without a real SECRET_KEY.
LOCAL_FALLBACK_SECRET_KEY = "local-development-insecure-secret-key"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    app_env: Literal["local", "production"] = "local"
    app_url: str = "http://localhost:8000"
    web_url: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://sightread:sightread@localhost:5432/sightread"
    postgres_user: str = "sightread"
    postgres_password: str = "sightread"  # noqa: S105 - compose default, not a secret
    postgres_db: str = "sightread"

    secret_key: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""

    auth_dev_mode: bool = False

    upload_max_bytes: int = 134_217_728
    page_cap: int = 500
    max_jobs_per_user: int = 2
    vision_concurrency_per_job: int = 8
    render_workers: int = 0  # 0 means "CPU count", resolved by the worker
    upload_dir: str = "/data/uploads"

    domain: str = ""
    acme_email: str = ""

    @model_validator(mode="after")
    def _check_secrets(self) -> Settings:
        if not self.secret_key:
            if self.app_env != "local":
                raise ValueError("SECRET_KEY is required when APP_ENV is not 'local'")
            self.secret_key = LOCAL_FALLBACK_SECRET_KEY
        return self

    @property
    def dev_login_enabled(self) -> bool:
        """`POST /api/auth/dev-login` exists only under both conditions (docs/auth.md)."""
        return self.app_env == "local" and self.auth_dev_mode

    @property
    def google_oidc_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
