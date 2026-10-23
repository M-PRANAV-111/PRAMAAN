"""Runtime configuration, read once from the environment and validated at startup."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

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
    public_base_url: str = "http://localhost:8000"
    email_provider: Literal["console", "smtp", "resend"] = "console"
    email_from: str = "PRAMAAN prototype <noreply@pramaan.local>"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str = ""
    smtp_password: str = Field(default="", repr=False)
    resend_api_key: str = Field(default="", repr=False)
    notify_email: bool = False
    job_timeout_seconds: float = Field(default=300, gt=0)
    backup_schedule: bool = False
    backup_hour_utc: int = Field(default=2, ge=0, le=23)
    backup_s3_endpoint: str = ""
    backup_s3_bucket: str = ""
    backup_s3_key_id: str = Field(default="", repr=False)
    backup_s3_secret: str = Field(default="", repr=False)
    log_format: Literal["text", "json"] = "text"
    metrics_token: str = Field(default="", repr=False)
    sentry_dsn: str = Field(default="", repr=False)
    trust_proxy: bool = False
    demo_accounts: bool = False

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
        url = urlsplit(self.public_base_url)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("PUBLIC_BASE_URL must be an absolute HTTP(S) URL without credentials, query or fragment")
        self.public_base_url = self.public_base_url.rstrip("/")
        if self.email_provider == "smtp" and not self.smtp_host:
            raise ValueError("SMTP_HOST is required for SMTP email")
        if self.email_provider == "resend" and not self.resend_api_key:
            raise ValueError("RESEND_API_KEY is required for Resend email")
        backup = (self.backup_s3_endpoint, self.backup_s3_bucket, self.backup_s3_key_id, self.backup_s3_secret)
        if any(backup) and not all(backup):
            raise ValueError("Set all four BACKUP_S3 settings together")
        if self.backup_s3_endpoint and urlsplit(self.backup_s3_endpoint).scheme != "https":
            raise ValueError("BACKUP_S3_ENDPOINT must use HTTPS")
        if self.env == "production":
            weak = self.jwt_secret.startswith("dev-only") or len(self.jwt_secret) < 32
            if weak:
                raise ValueError("JWT_SECRET must be set to a random value of at least 32 characters in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production (HTTPS only)")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS is not allowed in production")
            if url.scheme != "https" or url.hostname in ("localhost", "127.0.0.1", "::1"):
                raise ValueError("PUBLIC_BASE_URL must be set to a public HTTPS URL in production")
            if self.email_provider == "console":
                raise ValueError("Console email is forbidden in production")
            if self.demo_accounts or os.environ.get("SEED_DEMO_PASSWORD", "").strip():
                raise ValueError("Demo accounts are forbidden in production")
        return self

    @property
    def storage_dir(self) -> Path:
        return self.data_dir / "files"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = os.environ
    values: dict[str, object] = {
        "env": env.get("APP_ENV", "").strip() or "development",
        "cookie_secure": _env_bool("COOKIE_SECURE", False),
        "digilocker_enabled": _env_bool("DIGILOCKER_ENABLED", False),
        "notify_email": _env_bool("NOTIFY_EMAIL", False),
        "backup_schedule": _env_bool("BACKUP_SCHEDULE", False),
        "trust_proxy": _env_bool("TRUST_PROXY", bool(env.get("RAILWAY_ENVIRONMENT") or env.get("FLY_APP_NAME"))),
        "demo_accounts": _env_bool("DEMO_ACCOUNTS", False),
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
    for name in ("public_base_url", "email_provider", "email_from", "smtp_host", "smtp_port", "smtp_user",
                 "smtp_password", "resend_api_key", "job_timeout_seconds", "backup_hour_utc", "backup_s3_endpoint",
                 "backup_s3_bucket", "backup_s3_key_id", "backup_s3_secret", "log_format", "metrics_token", "sentry_dsn"):
        mapping[name.upper()] = name
    for key, field in mapping.items():
        if key in env and env[key].strip() != "":
            values[field] = env[key]
    return Settings(**values)


def reset_settings_cache() -> None:
    get_settings.cache_clear()
