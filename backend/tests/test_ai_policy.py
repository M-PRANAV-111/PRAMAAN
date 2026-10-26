"""Data policy: only documents that carry the SYNTHETIC stamp may reach an external provider."""
from __future__ import annotations

import io
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.ai import policy
from app.ai.config import AIConfig, AIConfigError, get_config, load_config, validate_startup
from app.db import reader
from synthetic import generator as g
from synthetic import variants as v
from tests.ai_support import PID, AICase, fixture
from tests.test_api import BACKEND
from datetime import date

STAMP = g.STAMP


def unstamped_noc(pages: int = 1, stamp_first_page: bool = False) -> bytes:
    """A certificate-like PDF that looks like the real thing: no SYNTHETIC stamp (the label the template misses)."""
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=A4)
    for page in range(pages):
        if stamp_first_page and page == 0:
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(40, A4[1] - 28, STAMP)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, A4[1] - 60, "FIRE SAFETY NO OBJECTION CERTIFICATE")
        c.setFont("Helvetica", 11)
        for i, line in enumerate(["Certificate No.: FNOC/REAL/0001", "Premises of: Synthetic institute (Synthetic)",
                                  f"Permanent Id: {PID}", "Date of Issue: 01-04-2025", "Expiry Date: 31-03-2027"]):
            c.drawString(40, A4[1] - 100 - 18 * i, line)
        c.showPage()
    c.save()
    return out.getvalue()


class StampTests(unittest.TestCase):
    def test_stamp_line_is_required_not_a_watermark_or_a_name(self):
        self.assertTrue(policy.page_has_stamp(STAMP))
        self.assertTrue(policy.page_has_stamp("noise\n" + STAMP.lower() + "\nmore"))
        for text in ("SYNTHETIC", "Shakti Institute of Technology (Synthetic)", "This is a synthetic example",
                     "NOT A REAL DOCUMENT", "", "Fire safety NOC for a real college"):
            with self.subTest(text=text):
                self.assertFalse(policy.page_has_stamp(text))

    def test_ocr_text_gets_a_small_tolerance_but_text_layers_do_not(self):
        garbled = "SYNTHETIC NOT A REAL D0CUMENT - generated for PRAMAAN testing"
        self.assertTrue(policy.page_has_stamp(garbled, ocr=True))
        self.assertFalse(policy.page_has_stamp(garbled, ocr=False))
        self.assertFalse(policy.page_has_stamp("SYNTHETIC REPORT ABOUT A REAL DOCUMENT LIBRARY", ocr=True))

    def test_every_page_that_would_be_sent_needs_the_stamp(self):
        cfg = AIConfig(provider="gemini")
        self.assertTrue(policy.decide(cfg, {1: STAMP, 2: STAMP}).allowed)
        blocked = policy.decide(cfg, {1: STAMP, 2: "second page without it"})
        self.assertEqual((blocked.allowed, blocked.reason), (False, "data_policy"))
        self.assertFalse(policy.decide(cfg, {}).allowed)

    def test_allow_real_skips_the_stamp_check(self):
        self.assertTrue(policy.decide(AIConfig(provider="gemini", data_policy="allow_real"), {1: "anything"}).allowed)


class StartupRefusalTests(unittest.TestCase):
    def test_allow_real_is_refused_without_the_paid_tier_flag(self):
        with self.assertRaises(AIConfigError):
            load_config({"AI_DATA_POLICY": "allow_real"})
        with self.assertRaises(AIConfigError):
            load_config({"AI_DATA_POLICY": "allow_real", "AI_PAID_TIER_CONFIRMED": "false"})
        self.assertEqual(load_config({"AI_DATA_POLICY": "allow_real", "AI_PAID_TIER_CONFIRMED": "true"}).data_policy, "allow_real")

    def test_validate_startup_raises_and_runtime_fails_closed(self):
        with patch.dict(os.environ, {"AI_PROVIDER": "gemini", "AI_DATA_POLICY": "allow_real", "AI_PAID_TIER_CONFIRMED": ""}):
            with self.assertRaises(AIConfigError):
                validate_startup()
            self.assertFalse(get_config().enabled)  # an unsafe setting can never switch AI on at runtime

    def test_the_application_refuses_to_start(self):
        def start(**env):
            return subprocess.run([sys.executable, "-c", "import app.main"], cwd=BACKEND, capture_output=True, text=True,
                                  env={**os.environ, "APP_ENV": "test", **env})
        refused = start(AI_PROVIDER="gemini", AI_DATA_POLICY="allow_real")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("AI_PAID_TIER_CONFIRMED", refused.stderr)
        self.assertEqual(start(AI_PROVIDER="gemini", AI_DATA_POLICY="allow_real", AI_PAID_TIER_CONFIRMED="true").returncode, 0)
        self.assertEqual(start().returncode, 0)


class PolicyPipelineTests(AICase):
    def test_non_synthetic_document_is_never_sent(self):
        with self.network(lambda call: self.fail("an external call was made for an unstamped document")) as net:
            doc = self.upload("fire_noc", "real.pdf", unstamped_noc())
        self.assertEqual(net.calls, [])
        self.assertEqual(self.last_job_notes(), ["AI step skipped: data_policy"])
        with reader() as c:
            state = c.execute("SELECT synthetic, step_status, skip_reason FROM ai_documents WHERE document_id=?", (doc,)).fetchone()
            job = c.execute("SELECT state FROM jobs ORDER BY created_at DESC").fetchone()
        self.assertEqual((state["synthetic"], state["step_status"], state["skip_reason"]), (0, "SKIPPED", "data_policy"))
        self.assertEqual(job["state"], "DONE")
        claims = self.claims(doc)
        self.assertIn("permanent_id", claims)            # the deterministic pipeline carried on
        self.assertNotIn("valid_to", claims)             # ...and nothing was filled in by AI

    def test_a_stamp_on_the_first_page_only_is_not_enough(self):
        with self.network(lambda call: self.fail("must not be called")) as net:
            self.upload("fire_noc", "two-page.pdf", unstamped_noc(pages=2, stamp_first_page=True))
        self.assertEqual(net.calls, [])
        self.assertEqual(self.last_job_notes(), ["AI step skipped: data_policy"])

    def test_synthetic_institution_name_does_not_open_the_gate(self):
        """The text says '(Synthetic)' in the institution name, which is exactly what a real upload could carry."""
        self.assertIn("(Synthetic)", "Premises of: Synthetic institute (Synthetic)")
        with self.network(lambda call: self.fail("must not be called")) as net:
            self.upload("fire_noc", "real.pdf", unstamped_noc())
        self.assertEqual(net.calls, [])

    def test_stamped_document_is_sent_and_only_that_document(self):
        pdf = v.fire_noc_variant("expiry_label", g.Inst("Synthetic institute", PID), "FNOC/SYN/AI/0001",
                                 date(2025, 4, 1), date(2027, 3, 31))
        with self.network(lambda call: fixture("extract_noc_expiry") if call.task == "extract" else fixture("explain_new_fact")) as net:
            self.upload("fire_noc", "noc.pdf", pdf)
        self.assertEqual(len(net.of("extract")), 1)
        parts = net.of("extract")[0].payload["input"]
        self.assertEqual([p["type"] for p in parts], ["document", "text"])   # one document, then the instructions
        self.assertNotIn("usr", str(net.of("extract")[0].payload))           # no user, institution or audit data

    def test_scanned_stamped_document_passes_the_ocr_tolerance(self):
        scan = g.rasterize(g.certificate("fire_noc", g.Inst("Synthetic institute", PID), "FNOC/SYN/AI/0005",
                                         date(2025, 4, 1), date(2027, 3, 31)))
        with self.network(lambda call: fixture("extract_noc_expiry")) as net:
            self.upload("fire_noc", "scan.pdf", scan)
        self.assertEqual(len(net.of("extract")), 1)

    def test_allow_real_with_the_paid_tier_flag_sends_unstamped_documents(self):
        with patch.dict(os.environ, {"AI_DATA_POLICY": "allow_real", "AI_PAID_TIER_CONFIRMED": "true"}):
            with self.network(lambda call: fixture("extract_noc_expiry")) as net:
                self.upload("fire_noc", "real.pdf", unstamped_noc())
        self.assertEqual(len(net.of("extract")), 1)

    def test_no_wording_request_for_an_application_that_holds_an_unstamped_document(self):
        """Even 'the fire NOC is missing' is information about the application, so nothing is sent for it."""
        stamped_summary = g.faculty_summary(g.Inst("Synthetic institute", PID), "2026-27", 60, 1200, 240)
        with self.network(lambda call: fixture("explain_new_fact")) as net:
            self.upload("faculty_summary", "summary.pdf", stamped_summary)   # all stamped so far: wording may be requested
            before = len(net.of("explain"))
            self.upload("fire_noc", "real.pdf", unstamped_noc())
        self.assertGreater(before, 0)
        self.assertEqual(len(net.of("explain")), before)                      # ...and not once the real file is in
        self.assertIn("AI step skipped: data_policy", self.last_job_notes())


if __name__ == "__main__":
    unittest.main()
