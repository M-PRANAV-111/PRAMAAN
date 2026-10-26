"""Pipeline-level behaviour of the AI step: the document-type check, and failing safe."""
from __future__ import annotations

import json
import unittest
from datetime import date

from app.ai.types import RateLimited, Unavailable
from app.db import reader
from app.pipeline import routing
from app.routes.common import finding_out
from synthetic import generator as g
from synthetic import variants as v
from tests.ai_support import PID, AICase, fixture, gemini_body

INST = g.Inst("Synthetic institute", PID)
NULL_NOC = gemini_body({"permanent_id": {"value": None, "page": None, "quote": None},
                        "valid_to": {"value": None, "page": None, "quote": None}})


def affidavit_pdf() -> bytes:
    return g.affidavit(INST, "2026-27", 240, 60, date(2026, 1, 7))


class ClassificationTests(AICase):
    """An affidavit uploaded in the fire-NOC slot."""

    def respond(self, classify_fixture):
        def respond(call):
            if call.task == "classify":
                return fixture(classify_fixture)
            if call.task == "extract":
                return NULL_NOC
            return fixture("explain_new_fact")
        return respond

    def type_findings(self):
        with reader() as c:
            return [dict(r) for r in c.execute("SELECT * FROM findings WHERE fingerprint LIKE 'INTEGRITY:AI_TYPE_MISMATCH%'")]

    def test_a_confident_quoted_mismatch_raises_a_review_finding_never_a_deficiency(self):
        with self.network(self.respond("classify_mismatch")) as net:
            self.upload("fire_noc", "wrong.pdf", affidavit_pdf())
        self.assertEqual(len(net.of("classify")), 1)
        (finding,) = self.type_findings()
        self.assertEqual((finding["title"], finding["severity"], finding["action_owner"], finding["state"]),
                         ("Uploaded file may not be a Fire safety NOC", "REVIEW", "OFFICER", "OPEN"))
        self.assertIn("AFFIDAVIT (FORMAT FOR EXTENSION OF APPROVAL)", finding["explanation"])   # the model's evidence quote
        self.assertIn("not a conclusion", finding["explanation"])
        proof = json.loads(finding["proof_json"])
        self.assertTrue(proof["detail"]["ai_assisted"])
        self.assertEqual(proof["detail"]["ai_type"], "affidavit")
        with reader() as c:
            rec = routing.compute(c, "app")
            out = finding_out(c, c.execute("SELECT * FROM findings WHERE id=?", (finding["id"],)).fetchone(), self.principal)
        self.assertIn("DOCUMENT_TYPE_MISMATCH", [r["code"] for r in rec.reasons])
        self.assertEqual((out["severity"], out["advisory"]), ("REVIEW", True))

    def test_the_finding_survives_revalidation_and_is_resolved_by_a_correct_upload(self):
        from app.db import transaction
        from app.pipeline.orchestrator import create_job, run_job
        with self.network(self.respond("classify_mismatch")):
            self.upload("fire_noc", "wrong.pdf", affidavit_pdf())
            with transaction() as c:
                job = create_job(c, "VALIDATE", "app")
            run_job(job)   # a full run reconciles findings again
        self.assertEqual([f["state"] for f in self.type_findings()], ["OPEN"])
        right = g.certificate("fire_noc", INST, "FNOC/SYN/AI/0020", date(2025, 4, 1), date(2027, 3, 31))
        with self.network(self.respond("classify_agree")):
            self.upload("fire_noc", "right.pdf", right)
        self.assertEqual([f["state"] for f in self.type_findings()], ["RESOLVED"])

    def test_not_confident_or_unquoted_answers_raise_nothing(self):
        import json as j
        from tests.ai_support import gemini_body as body
        cases = {
            "low confidence": body({"document_type": "affidavit", "confidence": 0.5, "evidence_quote": "AFFIDAVIT (FORMAT FOR EXTENSION OF APPROVAL)"}),
            "quote not on the page": body({"document_type": "affidavit", "confidence": 0.95, "evidence_quote": "SOLEMNLY SWORN BEFORE A NOTARY IN DELHI"}),
            "no quote": body({"document_type": "affidavit", "confidence": 0.95, "evidence_quote": None}),
            "agrees with the slot": body({"document_type": "fire_noc", "confidence": 0.99, "evidence_quote": "AFFIDAVIT (FORMAT FOR EXTENSION OF APPROVAL)"}),
        }
        for name, answer in cases.items():
            with self.subTest(name):
                self.setUp()
                responder = lambda call, answer=answer: answer if call.task == "classify" else (
                    NULL_NOC if call.task == "extract" else fixture("explain_new_fact"))
                with self.network(responder):
                    self.upload("fire_noc", "wrong.pdf", affidavit_pdf())
                self.assertEqual(self.type_findings(), [])
                self.tearDown()

    def test_a_document_that_the_keywords_recognise_is_not_sent_for_classification(self):
        right = g.certificate("fire_noc", INST, "FNOC/SYN/AI/0021", date(2025, 4, 1), date(2027, 3, 31))
        with self.network(lambda call: fixture("explain_new_fact")) as net:
            self.upload("fire_noc", "right.pdf", right)
        self.assertEqual(net.of("classify"), [])


class FailSafeTests(AICase):
    """Any AI failure leaves the deterministic result intact and says so on the job."""

    def noc(self):
        return v.fire_noc_variant("expiry_label", INST, "FNOC/SYN/AI/0001", date(2025, 4, 1), date(2027, 3, 31))

    def run_with(self, responder):
        with self.network(responder) as net:
            doc = self.upload("fire_noc", "noc.pdf", self.noc())
        with reader() as c:
            states = {r["state"] for r in c.execute("SELECT state FROM jobs")}
        return doc, net, states

    def assert_deterministic_only(self, doc, states):
        self.assertEqual(states, {"DONE"})
        claims = self.claims(doc)
        self.assertIn("permanent_id", claims)
        self.assertNotIn("valid_to", claims)
        self.assertTrue(any(n.startswith("AI step skipped:") for n in self.last_job_notes()), self.last_job_notes())
        with reader() as c:
            self.assertTrue(c.execute("SELECT 1 FROM routing_recommendations").fetchone())   # routing still ran

    def test_server_errors_on_every_model(self):
        doc, net, states = self.run_with(lambda call: Unavailable("http_503"))
        self.assertLessEqual(len(net.of("extract")), 3)
        self.assert_deterministic_only(doc, states)

    def test_timeouts(self):
        doc, net, states = self.run_with(lambda call: Unavailable("timeout"))
        self.assert_deterministic_only(doc, states)
        self.assertIn("AI step skipped: timeout", self.last_job_notes())

    def test_a_model_that_returns_garbage(self):
        garbage = {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": "not json"}]}]}
        doc, net, states = self.run_with(lambda call: garbage)
        self.assert_deterministic_only(doc, states)

    def test_rate_limit_moves_to_the_secondary_model_and_the_claim_is_still_grounded(self):
        calls = []

        def respond(call):
            calls.append(call.payload["model"])
            return RateLimited() if len(calls) == 1 else fixture("extract_noc_expiry")
        doc, net, states = self.run_with(respond)
        self.assertEqual(calls[:2], ["gemini-3.8-flash", "gemini-3.5-flash-lite"])
        self.assertEqual(self.claims(doc)["valid_to"]["extractor"], "ai+text")
        with reader() as c:
            self.assertEqual(c.execute("SELECT value FROM ai_state WHERE key='fallback_active'").fetchone()[0], "1")

    def test_a_crash_inside_the_step_is_contained(self):
        from unittest.mock import patch
        with patch("app.pipeline.ai_extract._integrate", side_effect=RuntimeError("boom")):
            doc, net, states = self.run_with(lambda call: fixture("extract_noc_expiry"))
        self.assert_deterministic_only(doc, states)
        self.assertIn("AI step skipped: error", self.last_job_notes())


if __name__ == "__main__":
    unittest.main()
