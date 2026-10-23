"""Finding wording: the template is the default; AI wording is used only when it adds no facts and passes validation."""
from __future__ import annotations

import json
import os
import unittest
from datetime import date
from unittest.mock import patch

from app.db import reader, transaction
from app.pipeline import explain
from app.routes.common import finding_out
from synthetic import generator as g
from tests.ai_support import PID, AICase, facts_in, fixture

INST = g.Inst("Synthetic institute", PID)
FACTS = {
    "rule_id": "INTAKE.CONSISTENT", "rule_title": "Intake is the same in the affidavit and the faculty summary",
    "severity": "REVIEW", "outcome": "FAIL", "reason": "values_disagree",
    "remedy": "Correct the document with the wrong intake and re-upload it.",
    "template_explanation": "The total intake differs: 300 in Affidavit (EoA format); 240 in Faculty & student strength summary.",
    "values": [{"document": "Affidavit (EoA format)", "field": "total intake", "value": "300", "page": 1},
               {"document": "Faculty & student strength summary", "field": "total intake", "value": "240", "page": 1}],
    "conflict": {"300": ["Affidavit (EoA format)"], "240": ["Faculty & student strength summary"]},
    "valid_to": "2026-03-31", "must_be_on_or_after": "2026-07-01", "inputs": {"ay": "2026-27"},
    "observed": [{"source": "Fire safety NOC", "value": "1-SYN-TEST"}],
}


class ValidationTests(unittest.TestCase):
    def check(self, text):
        return explain.validate(text, FACTS)

    def test_a_faithful_paraphrase_passes(self):
        for text in (
            "The intake differs between the documents: 300 in the affidavit and 240 in the faculty summary. "
            "Please correct the document with the wrong figure and upload it again.",
            "The total intake is 300 in the affidavit but 240 in the faculty summary.",
            "The fire certificate was valid until 31 March 2026, which is before 01-07-2026, the start of the academic year.",
            "Rule INTAKE.CONSISTENT found different intake figures.",
            "The academic year given is 2026-27.",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.check(text), (True, "ok"))

    def test_numbers_dates_ids_and_rule_ids_that_are_not_in_the_input_are_rejected(self):
        cases = {
            "The intake is 300 in the affidavit and 250 in the summary.": "new_fact",
            "The intake is 300, which is 60 fewer than the 360 allowed earlier.": "new_fact",
            "The certificate expired on 31-03-2025.": "new_fact",
            "The permanent id 1-SYN-9999-0000 is different.": "new_fact",
            "Rule FACULTY.RATIO also failed.": "new_fact",
            "The intake is 300 in the affidavit and about two hundred in the summary.": "number_word",
            "The certificate was valid until 31 May 2026.": "month_not_in_input",
        }
        for text, why in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.check(text), (False, why))

    def test_decision_vocabulary_is_rejected(self):
        for word in ("approved", "approve", "approving", "reject", "rejected", "rejection", "forged", "forgery", "fake",
                     "fraud", "fraudulent", "guarantee", "guaranteed"):
            with self.subTest(word=word):
                self.assertEqual(self.check(f"The intake of 300 is {word}.")[0], False)
        self.assertEqual(self.check("This relates to the Extension of Approval letter, with intake 300."), (True, "ok"))

    def test_length_and_markup(self):
        self.assertEqual(self.check("")[0], False)
        self.assertEqual(self.check("One. Two. Three. Four.")[0], False)
        self.assertEqual(self.check("A" * 700)[0], False)
        self.assertEqual(self.check("See https://example.test for 300.")[0], False)
        self.assertEqual(self.check("Use `300` here.")[0], False)
        self.assertEqual(self.check("First sentence about 300. Second about 240! Third?")[0], True)


class WordingPipelineTests(AICase):
    def run_bundle(self, text_fixture="explain_intake_valid"):
        def respond(call):
            facts = facts_in(call)
            return fixture(text_fixture) if facts["rule_id"] == "INTAKE.CONSISTENT" else fixture("explain_new_fact")
        with self.network(respond) as net:
            self.upload("affidavit", "aff.pdf", g.affidavit(INST, "2026-27", 300, 60, date(2026, 1, 7)))
            self.upload("faculty_summary", "summary.pdf", g.faculty_summary(INST, "2026-27", 60, 1200, 240))
        return net

    def finding(self, rule_id):
        with reader() as c:
            row = c.execute("SELECT * FROM findings WHERE rule_id=? ORDER BY created_at DESC", (rule_id,)).fetchone()
            return finding_out(c, row, self.principal), dict(row)

    def test_valid_wording_is_used_and_marked(self):
        self.run_bundle()
        out, row = self.finding("INTAKE.CONSISTENT")
        self.assertEqual((out["explanation_source"], out["ai_assisted"]), ("ai_checked", True))
        self.assertEqual(out["explanation"], json.loads(fixture("explain_intake_valid")["steps"][0]["content"][0]["text"])["text"])
        self.assertIn("300", row["explanation"])      # the template is still what the database holds
        self.assertNotEqual(out["explanation"], row["explanation"])
        self.assertEqual((out["title"], out["severity"], out["remedy"]), (row["title"], row["severity"], row["remedy"]))

    def test_rejected_wording_leaves_the_template(self):
        for name, why in (("explain_new_fact", "new_fact"), ("explain_forbidden", "forbidden_word"),
                          ("explain_injected", "forbidden_word")):
            with self.subTest(name):
                self.setUp()   # a clean database for each variant
                self.run_bundle(name)
                out, row = self.finding("INTAKE.CONSISTENT")
                self.assertEqual((out["explanation_source"], out["ai_assisted"], out["explanation"]),
                                 ("template", False, row["explanation"]))
                with reader() as c:
                    stored = c.execute("SELECT status, reject_reason FROM finding_ai_text WHERE finding_id=?", (row["id"],)).fetchone()
                self.assertEqual((stored["status"], stored["reject_reason"]), ("rejected", why))
                self.tearDown()

    def test_only_structured_proof_is_sent(self):
        net = self.run_bundle()
        calls = net.of("explain")
        self.assertTrue(calls)
        sent = json.dumps([c.payload for c in calls])
        for forbidden in ("aff.pdf", "summary.pdf", "doc_", "sha256", "bbox", "document_name", "%PDF", '"usr"', "fnd_"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, sent)
        for call in calls:
            self.assertEqual([p["type"] for p in call.payload["input"]], ["text"])   # no document part at all
        facts = next(facts_in(c) for c in calls if facts_in(c)["rule_id"] == "INTAKE.CONSISTENT")
        self.assertEqual({v["value"] for v in facts["values"]}, {"300", "240"})
        self.assertTrue(all(v["page"] == 1 for v in facts["values"]))
        self.assertEqual(set(facts["conflict"]), {"300", "240"})

    def test_only_rule_findings_are_reworded(self):
        net = self.run_bundle()
        self.assertTrue(all(facts_in(c)["rule_id"] for c in net.of("explain")))

    def test_unchanged_proof_is_not_requested_again(self):
        net = self.run_bundle()
        first = len(net.of("explain"))
        from app.pipeline.orchestrator import create_job, run_job
        with transaction() as c:
            job = create_job(c, "VALIDATE", "app")
        with self.network(lambda call: self.fail("must not be called again")):
            run_job(job)
        self.assertGreater(first, 0)

    def test_kill_switch_and_provider_none_show_templates_again(self):
        self.run_bundle()
        out, _ = self.finding("INTAKE.CONSISTENT")
        self.assertEqual(out["explanation_source"], "ai_checked")
        with patch.dict(os.environ, {"AI_PROVIDER": "none"}):
            self.assertEqual(self.finding("INTAKE.CONSISTENT")[0]["explanation_source"], "template")
        with transaction() as c:
            c.execute("INSERT INTO ai_state (key, value, updated_at) VALUES ('kill_switch','1','now')")
        self.assertEqual(self.finding("INTAKE.CONSISTENT")[0]["explanation_source"], "template")

    def test_wording_is_dropped_when_the_proof_changes(self):
        self.run_bundle()
        with transaction() as c:
            c.execute("UPDATE findings SET proof_json = replace(proof_json, '\"240\"', '\"241\"') WHERE rule_id='INTAKE.CONSISTENT'")
        self.assertEqual(self.finding("INTAKE.CONSISTENT")[0]["explanation_source"], "template")


if __name__ == "__main__":
    unittest.main()
