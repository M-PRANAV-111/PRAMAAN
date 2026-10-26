"""A6: every production refusal has its own test.

Each test starts from a production configuration that is accepted (``test_valid_production_configuration_starts``)
and changes exactly one thing. The existing ``test_config.test_production_guards`` loop stays as it is.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app.ai.config import AIConfigError, load_config
from app.config import Settings, reset_settings_cache
from tests.local_support import LocalDatabaseCase
from tests.test_api import BACKEND

PRODUCTION_ENV = {
    "APP_ENV": "production", "JWT_SECRET": "x" * 48, "COOKIE_SECURE": "true",
    "PUBLIC_BASE_URL": "https://pramaan.example.test", "EMAIL_PROVIDER": "smtp", "SMTP_HOST": "smtp.example.test",
    "CORS_ORIGINS": "", "DEMO_ACCOUNTS": "false", "SHOW_DEMO_ACCOUNTS": "false", "SEED_DEMO_PASSWORD": "",
    "AI_PROVIDER": "none", "AI_TEST_FAULT": "", "AI_DATA_POLICY": "synthetic_only", "AI_PAID_TIER_CONFIRMED": "",
    "BACKUP_S3_ENDPOINT": "", "BACKUP_S3_BUCKET": "", "BACKUP_S3_KEY_ID": "", "BACKUP_S3_SECRET": "",
}


def production(**overrides) -> Settings:
    values = {"env": "production", "jwt_secret": secrets.token_urlsafe(40), "cookie_secure": True,
              "public_base_url": "https://pramaan.example.test", "email_provider": "smtp", "smtp_host": "smtp.example.test"}
    return Settings(**{**values, **overrides})


class SettingsRefusals(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ, {"SEED_DEMO_PASSWORD": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def refused(self, message: str, **overrides):
        with self.assertRaises(ValueError) as caught:
            production(**overrides)
        self.assertIn(message, str(caught.exception))

    def test_valid_production_configuration_is_accepted(self):
        self.assertEqual(production().env, "production")

    def test_short_jwt_secret(self):
        self.refused("JWT_SECRET", jwt_secret="too-short")

    def test_development_jwt_secret(self):
        self.refused("JWT_SECRET", jwt_secret="dev-only-" + "x" * 40)

    def test_cookie_not_secure(self):
        self.refused("COOKIE_SECURE", cookie_secure=False)

    def test_wildcard_cors(self):
        self.refused("Wildcard CORS", cors_origins=["*"])

    def test_http_public_base_url(self):
        self.refused("public HTTPS URL", public_base_url="http://pramaan.example.test")

    def test_localhost_public_base_url(self):
        self.refused("public HTTPS URL", public_base_url="https://localhost")

    def test_console_email(self):
        self.refused("Console email", email_provider="console")

    def test_demo_accounts(self):
        self.refused("Demo accounts", demo_accounts=True)

    def test_show_demo_accounts(self):
        self.refused("Demo accounts", show_demo_accounts=True)

    def test_seed_demo_password_set(self):
        with patch.dict(os.environ, {"SEED_DEMO_PASSWORD": "any-value"}):
            self.refused("Demo accounts")


class AIRefusals(unittest.TestCase):
    def test_fixture_provider(self):
        with self.assertRaises(AIConfigError):
            load_config({**PRODUCTION_ENV, "AI_PROVIDER": "fixture"})

    def test_test_fault(self):
        with self.assertRaises(AIConfigError):
            load_config({**PRODUCTION_ENV, "AI_PROVIDER": "gemini", "AI_TEST_FAULT": "timeout"})

    def test_real_documents_without_paid_tier(self):
        with self.assertRaises(AIConfigError):
            load_config({**PRODUCTION_ENV, "AI_PROVIDER": "gemini", "AI_DATA_POLICY": "allow_real"})


class RuntimeRefusals(LocalDatabaseCase):
    """Refusals that act on a running system rather than on the configuration."""

    def to_production(self):
        patcher = patch.dict(os.environ, {**PRODUCTION_ENV, "DATA_DIR": self.tmp.name, "DATABASE_PATH": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(reset_settings_cache)
        reset_settings_cache()

    def test_synthetic_accounts_in_the_database_stop_startup(self):
        from app.db import now_iso, transaction
        from app.main import bootstrap
        with transaction() as c:
            c.execute("INSERT INTO users (id,email,name,role,institution_id,password_hash,created_at)"
                      " VALUES ('syn','officer@aicte.synthetic.in','Synthetic','OFFICER',NULL,'!x',?)", (now_iso(),))
        self.to_production()
        with self.assertRaises(RuntimeError):
            bootstrap()

    def test_console_email_cannot_send(self):
        """Defence in depth: even a process that somehow holds console email in production writes nothing."""
        from app import email
        self.to_production()
        with patch.object(email, "get_settings", _console_in_production), self.assertRaises(RuntimeError):
            email._deliver("someone@example.test", "Subject", "Body", None)
        self.assertFalse((self.tmp_path() / "outbox").exists() and any((self.tmp_path() / "outbox").iterdir()))

    def tmp_path(self):
        from pathlib import Path
        return Path(self.tmp.name)

    def test_demo_account_chips_are_not_offered(self):
        """Second guard: even with the flag forced on in production, /meta does not offer demo chips."""
        from app.routes import system
        self.to_production()
        forced = production()
        object.__setattr__(forced, "show_demo_accounts", True)
        with patch.object(system, "get_settings", lambda: forced):
            self.assertFalse(system.meta(None)["features"]["demo_accounts"])
        dev = Settings(env="test", show_demo_accounts=True)
        with patch.object(system, "get_settings", lambda: dev):
            self.assertTrue(system.meta(None)["features"]["demo_accounts"])  # control: the flag works outside production


def _console_in_production() -> Settings:
    """Settings refuse console email in production; build the state a misconfigured process would be in."""
    s = production()
    object.__setattr__(s, "email_provider", "console")
    return s


class StartupProcess(unittest.TestCase):
    def test_application_refuses_to_start_with_demo_accounts_in_production(self):
        with tempfile.TemporaryDirectory() as data:
            env = {**os.environ, **PRODUCTION_ENV, "DATA_DIR": data, "DATABASE_PATH": "", "DEMO_ACCOUNTS": "true"}
            run = subprocess.run([sys.executable, "-c", "from app.config import get_settings; get_settings()"],
                                 cwd=BACKEND, env=env, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("Demo accounts are forbidden in production", run.stderr)
            env["DEMO_ACCOUNTS"] = "false"
            ok = subprocess.run([sys.executable, "-c", "from app.config import get_settings; get_settings()"],
                                cwd=BACKEND, env=env, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)


if __name__ == "__main__":
    unittest.main()
