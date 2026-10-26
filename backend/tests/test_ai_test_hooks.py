"""The test-only hooks of the AI layer: the recorded fixture provider and AI_TEST_FAULT (B6).

Both exist so a real server started by the browser suite can exercise the AI path with no key and no network.
They must be refused everywhere except APP_ENV=test, and an injected failure must leave the deterministic result.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from datetime import date
from unittest.mock import patch

from app.ai.client import build_status, usage_today
from app.ai.config import AIConfigError, load_config
from app.db import reader
from synthetic import generator as g
from synthetic import variants as v
from tests.ai_support import PID, AICase
from tests.test_api import BACKEND

INST = g.Inst("Synthetic institute", PID)


def table_affidavit() -> bytes:
    """The document the recorded fixture answers for: the template extractor reads none of its fields."""
    return v.affidavit_variant("two_column", INST, "2026-27", 120, 60, date(2026, 1, 7))


def no_network(*_args, **_kwargs):
    raise AssertionError("the fixture provider or an injected fault reached the network")


class RefusalTests(unittest.TestCase):
    def test_fixture_provider_is_refused_outside_test(self):
        for app_env in ("development", "production", ""):
            with self.subTest(app_env=app_env), self.assertRaises(AIConfigError):
                load_config({"AI_PROVIDER": "fixture", "APP_ENV": app_env})

    def test_test_fault_is_refused_outside_test(self):
        for app_env in ("development", "production", ""):
            with self.subTest(app_env=app_env), self.assertRaises(AIConfigError):
                load_config({"AI_PROVIDER": "gemini", "AI_TEST_FAULT": "rate_limit", "APP_ENV": app_env})

    def test_unknown_fault_is_refused(self):
        with self.assertRaises(AIConfigError):
            load_config({"AI_PROVIDER": "fixture", "AI_TEST_FAULT": "slow", "APP_ENV": "test"})

    def test_the_application_refuses_to_start_with_a_fixture_outside_test(self):
        def start(**env):
            return subprocess.run([sys.executable, "-c", "import app.main"], cwd=BACKEND, capture_output=True, text=True,
                                  env={**os.environ, "AI_TEST_FAULT": "", "AI_PROVIDER": "none", **env})
        refused = start(APP_ENV="development", AI_PROVIDER="fixture")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("require APP_ENV=test", refused.stderr)
        self.assertEqual(start(APP_ENV="test", AI_PROVIDER="fixture", AI_TEST_FAULT="timeout").returncode, 0)


class FixtureProviderTests(AICase):
    env_extra = {"AI_PROVIDER": "fixture", "AI_TEST_FAULT": ""}

    def test_printed_value_is_grounded_and_the_rest_stays_a_suggestion(self):
        with patch("app.ai.http.post_json", no_network):
            doc = self.upload("affidavit", "table.pdf", table_affidavit())
        claims = self.claims(doc)
        intake = claims["total_intake"]
        self.assertEqual((intake["value_norm"], intake["extractor"]), ("120", "ai+text"))
        self.assertLess(intake["x0"], intake["x1"])  # a real box on the page, taken from the page, not the answer
        self.assertLess(intake["y0"], intake["y1"])
        self.assertNotEqual((claims.get("faculty_count") or {}).get("value_norm"), "999999")
        self.assertEqual([(s["field"], s["value"], s["reason"]) for s in self.suggestions(doc)],
                         [("faculty_count", "999999", "conflicts_with_page")])  # the page says 60
        self.assertIn("ai.extraction", self.audit_actions())

    def test_status_labels_the_fixture_as_simulated(self):
        with reader() as c:
            status = build_status(c)
        self.assertEqual((status["provider"], status["simulated"]), ("fixture", True))
        self.assertEqual(status["models"]["primary"], "fixture:recorded-test-fixture")


class FaultInjectionTests(AICase):
    """Each fault fails the request before anything is sent; the deterministic extraction stands."""

    def run_fault(self, fault: str) -> tuple[dict, list[str], dict]:
        with patch.dict(os.environ, {"AI_PROVIDER": "fixture", "AI_TEST_FAULT": fault}), \
                patch("app.ai.http.post_json", no_network):
            doc = self.upload("affidavit", "table.pdf", table_affidavit())
            with reader() as c:
                status = build_status(c)
        return self.claims(doc), self.last_job_notes(), status

    def test_rate_limit(self):
        claims, notes, status = self.run_fault("rate_limit")
        self.assertFalse([c for c in claims.values() if c["extractor"].startswith("ai+")])
        self.assertEqual(notes, ["AI step skipped: rate_limited"])
        self.assertEqual((status["last_error_code"], status["fallback_active"]), ("rate_limited", True))
        with reader() as c:
            used = usage_today(c)
        # Extraction and the finding wording each try once; every request failed and every one is accounted.
        self.assertGreaterEqual(status["requests_today"], 1)
        self.assertEqual(used["failures"], status["requests_today"])

    def test_timeout(self):
        claims, notes, status = self.run_fault("timeout")
        self.assertFalse([c for c in claims.values() if c["extractor"].startswith("ai+")])
        self.assertEqual(notes, ["AI step skipped: timeout"])
        self.assertEqual(status["last_error_code"], "timeout")

    def test_invalid_json(self):
        claims, notes, status = self.run_fault("invalid_json")
        self.assertFalse([c for c in claims.values() if c["extractor"].startswith("ai+")])
        self.assertEqual(notes, ["AI step skipped: schema_violation"])
        self.assertEqual(status["last_error_code"], "schema_violation")

    def test_findings_and_claims_match_ai_off(self):
        def signature(app_id):
            with reader() as c:
                findings = sorted((r["rule_id"], r["severity"], r["state"]) for r in
                                  c.execute("SELECT rule_id, severity, state FROM findings WHERE application_id=?", (app_id,)))
                claims = sorted((r["field"], r["value_norm"], r["extractor"]) for r in
                                c.execute("SELECT field, value_norm, extractor FROM claims WHERE application_id=?", (app_id,)))
            return findings, claims
        self.run_fault("rate_limit")
        off = self.second_application()
        with patch.dict(os.environ, {"AI_PROVIDER": "none", "AI_TEST_FAULT": ""}):
            self.upload("affidavit", "table.pdf", table_affidavit(), app=off)
        self.assertEqual(signature("app"), signature(off))


if __name__ == "__main__":
    unittest.main()
