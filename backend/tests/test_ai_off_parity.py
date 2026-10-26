"""AI_PROVIDER=none leaves the existing pipeline exactly as it was.

``fixtures/ai/parity_snapshot.json`` was produced by the pipeline *before* the AI layer existed (see
``tests/parity_support.py``). The same seeded scenarios, re-run now with the layer installed but switched off, must give
identical findings, statuses, claims, verification outcomes and repair plans.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from app.db import reader
from app.features import snapshot
from synthetic import generator as g
from synthetic import variants as v
from tests import parity_support
from tests.ai_support import PID, AICase


class ParityTests(unittest.TestCase):
    def test_seeded_scenarios_match_the_pre_ai_snapshot(self):
        expected = json.loads(parity_support.SNAPSHOT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            actual = parity_support.build(tmp)
        self.assertEqual(sorted(actual["applications"]), sorted(expected["applications"]))
        for name, entry in expected["applications"].items():
            for key in ("status", "findings", "repair_plan", "documents"):
                with self.subTest(application=name, part=key):
                    self.assertEqual(actual["applications"][name][key], entry[key])


class OffMeansOffTests(AICase):
    env_extra = {"AI_PROVIDER": "none"}

    def test_nothing_is_attempted_recorded_or_changed(self):
        pdf = v.fire_noc_variant("expiry_label", g.Inst("Synthetic institute", PID), "FNOC/SYN/AI/0001",
                                 date(2025, 4, 1), date(2027, 3, 31))     # a layout that would trigger the AI step
        with patch("requests.post", side_effect=AssertionError("network used with AI off")):
            doc = self.upload("fire_noc", "noc.pdf", pdf)
        self.assertNotIn("valid_to", self.claims(doc))
        with reader() as c:
            for table in ("ai_cache", "ai_usage_daily", "ai_documents", "ai_suggestions", "finding_ai_text", "job_notes", "ai_state"):
                with self.subTest(table=table):
                    self.assertEqual(c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
            self.assertFalse(c.execute("SELECT 1 FROM claims WHERE extractor LIKE 'ai+%'").fetchone())
            self.assertTrue(c.execute("SELECT 1 FROM routing_recommendations").fetchone())   # routing is always on

    def test_feature_flags(self):
        flags = snapshot()
        self.assertTrue(flags["routing"])
        self.assertFalse(flags["ai"])


if __name__ == "__main__":
    unittest.main()
