"""Runtime configuration, read once from the environment and validated at startup."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    env: str = Field(default="development", pattern="^(development|test|production)$")
    data_dir: Path = BACKEND_DIR / "var"
    database_path: Path | None = None
    rulepack_dir: Path = BACKEND_DIR / "rulepacks"
    front_dist: Path | None = None
    jwt_secret: str = "dev-only-insecure-secret-change-me-0123456789"
    jwt_ttl_minutes: int = 30
    cookie_secure: bool = False
    cors_origins: list[str] = []
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pdf_pages: int = 40
    login_rate_per_minute: int = 10
    upload_rate_per_minute: int = 30
    tesseract_cmd: str | None = None
    worker_threads: int = 1
    # External integrations stay disabled unless explicitly configured AND authorized.
    digilocker_enabled: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _derive_and_check(self) -> "Settings":
        if self.database_path is None:
            self.database_path = self.data_dir / "pramaan.sqlite3"
        if self.env == "production":
            weak = self.jwt_secret.startswith("dev-only") or len(self.jwt_secret) < 32
            if weak:
                raise ValueError("JWT_SECRET must be set to a random value of at least 32 characters in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production (HTTPS only)")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS is not allowed in production")
        return self

    @property
    def storage_dir(self) -> Path:
        return self.data_dir / "files"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = os.environ
    values: dict[str, object] = {
        "env": env.get("APP_ENV", "development"),
        "cookie_secure": _env_bool("COOKIE_SECURE", False),
        "digilocker_enabled": _env_bool("DIGILOCKER_ENABLED", False),
    }
    mapping = {
        "DATA_DIR": "data_dir",
        "DATABASE_PATH": "database_path",
        "RULEPACK_DIR": "rulepack_dir",
        "FRONT_DIST": "front_dist",
        "JWT_SECRET": "jwt_secret",
        "JWT_TTL_MINUTES": "jwt_ttl_minutes",
        "CORS_ORIGINS": "cors_origins",
        "MAX_UPLOAD_BYTES": "max_upload_bytes",
        "MAX_PDF_PAGES": "max_pdf_pages",
        "LOGIN_RATE_PER_MINUTE": "login_rate_per_minute",
        "UPLOAD_RATE_PER_MINUTE": "upload_rate_per_minute",
        "TESSERACT_CMD": "tesseract_cmd",
        "WORKER_THREADS": "worker_threads",
    }
    for key, field in mapping.items():
        if key in env and env[key] != "":
            values[field] = env[key]
    return Settings(**values)


def reset_settings_cache() -> None:
    get_settings.cache_clear()
