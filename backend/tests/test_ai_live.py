"""Opt-in smoke tests against the real providers. Skipped unless AI_LIVE_TEST=1 and a key is set.

    AI_LIVE_TEST=1 GEMINI_API_KEY=... python -m unittest tests.test_ai_live -v

They send one synthetic, SYNTHETIC-stamped document (no real data) and check only that the response validates
against the schema; they never assert what the model read. CI does not run them.
"""
from __future__ import annotations

import os
import unittest
from datetime import date

from app.ai.gemini import GeminiProvider
from app.ai.groq import GroqProvider
from app.ai.types import ExplainRequest, ExtractRequest, FieldInfo
from app.pipeline import extract
from app.ai import ground
from synthetic import generator as g
from synthetic import variants as v

LIVE = os.environ.get("AI_LIVE_TEST") == "1"
FIELDS = [FieldInfo("permanent_id", "Permanent ID", "id"), FieldInfo("valid_to", "validity date", "date")]


def synthetic_noc() -> bytes:
    return v.fire_noc_variant("expiry_label", g.Inst("Live Smoke Institute (Synthetic)", "1-SYN-LIVE-0001"),
                              "FNOC/SYN/LIVE/0001", date(2025, 4, 1), date(2027, 3, 31))


@unittest.skipUnless(LIVE and os.environ.get("GEMINI_API_KEY"), "set AI_LIVE_TEST=1 and GEMINI_API_KEY")
class GeminiLive(unittest.TestCase):
    def provider(self) -> GeminiProvider:
        return GeminiProvider(os.environ["GEMINI_API_KEY"], os.environ.get("AI_MODEL_PRIMARY", "gemini-3.8-flash"), 60)

    def test_extract_validates(self):
        pdf = synthetic_noc()
        result = self.provider().extract(ExtractRequest("fire_noc", "Fire safety NOC", FIELDS, pdf, [1]))
        self.assertEqual(set(result.fields), {"permanent_id", "valid_to"})
        pages = ground.pages_from(extract.extract_pdf(pdf))
        proposal = result.fields["valid_to"]
        print(f"\nlive gemini model={result.model} latency_ms={result.usage.latency_ms} tokens="
              f"{result.usage.input_tokens}/{result.usage.output_tokens} valid_to grounded="
              f"{bool(proposal.value and ground.ground('valid_to', 'date', proposal.value, proposal.page, proposal.quote, pages).claim)}")

    def test_explain_validates(self):
        result = self.provider().explain(ExplainRequest({"rule_id": "FIRE.VALID", "valid_to": "2026-03-31",
                                                         "must_be_on_or_after": "2026-07-01"}))
        self.assertTrue(result.text)


@unittest.skipUnless(LIVE and os.environ.get("GROQ_API_KEY"), "set AI_LIVE_TEST=1 and GROQ_API_KEY")
class GroqLive(unittest.TestCase):
    def test_extract_validates_from_local_text(self):
        result = extract.extract_pdf(synthetic_noc())
        text = {1: ground.page_texts(result)[1]}
        out = GroqProvider(os.environ["GROQ_API_KEY"], os.environ.get("AI_FALLBACK_MODEL", "openai/gpt-oss-120b"), 60).extract(
            ExtractRequest("fire_noc", "Fire safety NOC", FIELDS, None, [1], text))
        self.assertEqual(set(out.fields), {"permanent_id", "valid_to"})


if __name__ == "__main__":
    unittest.main()
