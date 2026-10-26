"""Routing recommendation: every outcome from crafted runs, and the guarantees around it."""
from __future__ import annotations

import json
import unittest
from datetime import date

from app.db import dumps, new_id, now_iso, reader, transaction
from app.pipeline import routing
from app.pipeline.ai_extract import read_fields_by_type
from app.rulepacks import active_version
from tests.ai_support import AICase
from tests.core_support import CoreApiCase

OUTCOMES = {"READY_FOR_SCRUTINY", "CORRECTIONS_REQUIRED", "OFFICER_REVIEW_REQUIRED"}
LADDER = ("eoa_letter", "fire_noc", "building_stability")


class Crafted(AICase):
    """Builds the database state the pipeline would leave behind, so each recommendation can be reasoned about."""
    env_extra = {"AI_PROVIDER": "none"}

    def craft(self, *, skip_docs=(), verification="VERIFIED", simulated=False, issuer_key_simulated=False, confidence=0.98,
              outcomes=None, app="app"):
        with transaction() as c:
            row, pack = active_version(c)
            ts = now_iso()
            self.doc_ids = {}
            reads = read_fields_by_type(pack)
            for item in pack.checklist:
                if not item.required or item.doc_type in skip_docs:
                    continue
                did = new_id("doc")
                self.doc_ids[item.doc_type] = did
                c.execute("INSERT INTO documents (id, application_id, doc_type, original_name, sha256, size_bytes, mime, pages,"
                          " uploaded_by, uploaded_at, processing_state, verification_status) VALUES"
                          " (?,?,?,?,?,?,?,?,?,?, 'DONE', ?)",
                          (did, app, item.doc_type, f"{item.doc_type}.pdf", "0" * 64, 10, "application/pdf", 1, "usr", ts,
                           verification if item.doc_type in LADDER else None))
                for field in reads.get(item.doc_type, ()):
                    c.execute("INSERT INTO claims (id,document_id,application_id,field,value_raw,value_norm,value_type,page,"
                              "x0,y0,x1,y1,page_width,page_height,extractor,confidence) VALUES"
                              " (?,?,?,?,?,?,?,1,0,0,1,1,595,842,'text-layer+template',?)",
                              (new_id("clm"), did, app, field, "1", "1", "text", confidence))
                if item.doc_type in LADDER:
                    c.execute("INSERT INTO verifications (id, document_id, application_id, tier, channel, status, simulated,"
                              " request_ref, response_hash, detail_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (new_id("ver"), did, app, 1, "signed_qr", verification, int(simulated), None, "h",
                               dumps({"issuer_key_simulated": issuer_key_simulated}), ts))
            self.run_id = new_id("run")
            c.execute("INSERT INTO validation_runs (id, application_id, rule_pack_version_id, trigger, affected_rules_json,"
                      " started_at, finished_at) VALUES (?,?,?,?,?,?,?)", (self.run_id, app, row["id"], "test", "[]", ts, ts))
            for rule in pack.rules:
                outcome = (outcomes or {}).get(rule.id, "PASS")
                proof = {"missing": {"reason": "missing_field", "input": "x"}} if outcome == "NOT_EVALUABLE" else {}
                c.execute("INSERT INTO rule_results (id, run_id, application_id, rule_id, outcome, proof_json) VALUES (?,?,?,?,?,?)",
                          (new_id("rr"), self.run_id, app, rule.id, outcome, dumps(proof)))

    def finding(self, fingerprint, *, source="RULE", rule_id=None, severity="REVIEW", owner="OFFICER", state="OPEN",
                fix_doc_type=None, title="A finding", app="app"):
        fid = new_id("fnd")
        with transaction() as c:
            c.execute("INSERT INTO findings (id, application_id, run_id, fingerprint, source_kind, rule_id, title, severity,"
                      " state, explanation, remedy, fix_doc_type, action_owner, proof_json, evidence_json, advisory, created_at)"
                      " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)",
                      (fid, app, self.run_id, fingerprint, source, rule_id, title, severity, state, "explanation", "remedy",
                       fix_doc_type, owner, "{}", "[]", now_iso()))
        return fid

    def recommend(self, app="app"):
        with reader() as c:
            return routing.compute(c, app)

    def codes(self, rec):
        return [r["code"] for r in rec.reasons]


class OutcomeTests(Crafted):
    def test_ready_only_when_everything_is_certain(self):
        self.craft()
        rec = self.recommend()
        self.assertEqual(rec.outcome, "READY_FOR_SCRUTINY")
        self.assertEqual(self.codes(rec), ["NO_OPEN_ISSUES"])
        self.assertEqual(rec.queue_flag, "NO_OPEN_FINDINGS")
        self.assertFalse(rec.ai_used)

    def test_simulated_only_verification_goes_to_an_officer(self):
        self.craft(simulated=True)
        rec = self.recommend()
        self.assertEqual(rec.outcome, "OFFICER_REVIEW_REQUIRED")
        self.assertEqual(set(self.codes(rec)), {"SIMULATED_SOURCE_ONLY"})
        self.assertEqual(len(rec.reasons), len(LADDER))

    def test_a_signed_source_whose_issuer_key_is_synthetic_is_not_enough(self):
        self.craft(issuer_key_simulated=True)
        self.assertEqual(self.recommend().outcome, "OFFICER_REVIEW_REQUIRED")

    def test_low_confidence_goes_to_an_officer_and_the_threshold_is_exact(self):
        self.craft(confidence=0.80)
        rec = self.recommend()
        self.assertEqual(rec.outcome, "OFFICER_REVIEW_REQUIRED")
        self.assertIn("LOW_CONFIDENCE_CLAIM", self.codes(rec))
        self.assertTrue(all(r["document_id"] for r in rec.reasons if r["code"] == "LOW_CONFIDENCE_CLAIM"))
        self.setUp()
        self.craft(confidence=0.85)
        self.assertEqual(self.recommend().outcome, "READY_FOR_SCRUTINY")

    def test_unconfirmed_ai_suggestions_on_fields_the_rules_read_block_ready(self):
        self.craft()
        with transaction() as c:
            c.execute("INSERT INTO ai_suggestions (id, document_id, application_id, field, value, page, quote, reason, model,"
                      " status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (new_id("sug"), self.doc_ids["fire_noc"], "app", "valid_to", "31-12-2099", 1, None, "low_confidence",
                       "m", "OPEN", now_iso()))
        rec = self.recommend()
        self.assertEqual((rec.outcome, self.codes(rec)), ("OFFICER_REVIEW_REQUIRED", ["AI_SUGGESTION_UNCONFIRMED"]))
        with transaction() as c:
            c.execute("UPDATE ai_suggestions SET status='DISMISSED'")
        self.assertEqual(self.recommend().outcome, "READY_FOR_SCRUTINY")
        with transaction() as c:  # a suggestion for a field no rule reads is only information
            c.execute("INSERT INTO ai_suggestions (id, document_id, application_id, field, value, page, quote, reason, model,"
                      " status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (new_id("sug"), self.doc_ids["fire_noc"], "app", "ref_no", "X", 1, None, "low_confidence", "m", "OPEN",
                       now_iso()))
        self.assertEqual(self.recommend().outcome, "READY_FOR_SCRUTINY")

    def test_open_integrity_duplicate_and_type_mismatch_indicators(self):
        for fingerprint, source, code in (("INTEGRITY:INCREMENTAL_UPDATE:fire_noc:", "INTEGRITY", "INTEGRITY_INDICATOR_OPEN"),
                                          ("DUPLICATE:infra_photo:doc_x", "DUPLICATE", "DUPLICATE_INDICATOR_OPEN"),
                                          ("INTEGRITY:AI_TYPE_MISMATCH:fire_noc:", "INTEGRITY", "DOCUMENT_TYPE_MISMATCH")):
            with self.subTest(code=code):
                self.setUp()
                self.craft()
                fid = self.finding(fingerprint, source=source)
                rec = self.recommend()
                self.assertEqual((rec.outcome, self.codes(rec)), ("OFFICER_REVIEW_REQUIRED", [code]))
                self.assertEqual(rec.reasons[0]["finding_id"], fid)
                with transaction() as c:
                    c.execute("UPDATE findings SET state='DISMISSED'")
                self.assertEqual(self.recommend().outcome, "READY_FOR_SCRUTINY")

    def test_duplicate_reason_reveals_nothing_about_the_other_institution(self):
        self.craft()
        self.finding("DUPLICATE:infra_photo:doc_x", source="DUPLICATE", title="Possible reuse of evidence from another application")
        text = json.dumps(self.recommend().reasons)
        self.assertNotIn("doc_x", text)

    def test_uncertain_rule_results_go_to_an_officer(self):
        self.craft(outcomes={"FACULTY.RATIO": "NOT_EVALUABLE"})
        rec = self.recommend()
        self.assertEqual((rec.outcome, self.codes(rec)), ("OFFICER_REVIEW_REQUIRED", ["RULE_NOT_EVALUABLE"]))
        self.setUp()
        self.craft(outcomes={"ID.CONSISTENT": "FAIL"})
        self.assertEqual(self.codes(self.recommend()), ["REVIEW_FINDING_OPEN"])

    def test_verification_statuses_other_than_verified(self):
        for status, code in (("SOURCE_UNAVAILABLE", "SOURCE_UNAVAILABLE"), ("MANUAL_REVIEW_REQUIRED", "MANUAL_REVIEW_REQUIRED"),
                             ("MISMATCH_DETECTED", "VERIFICATION_MISMATCH"), ("VERIFICATION_PENDING", "VERIFICATION_PENDING")):
            with self.subTest(status=status):
                self.setUp()
                self.craft(verification=status)
                rec = self.recommend()
                self.assertEqual((rec.outcome, set(self.codes(rec))), ("OFFICER_REVIEW_REQUIRED", {code}))

    def test_institution_owned_deficiency_means_corrections_and_officer_reasons_are_still_listed(self):
        self.craft(outcomes={"FIRE.VALID": "FAIL"}, verification="SOURCE_UNAVAILABLE")
        self.finding("RULE:FIRE.VALID", rule_id="FIRE.VALID", severity="DEFICIENCY", owner="INSTITUTION", fix_doc_type="fire_noc",
                     title="Fire safety NOC valid at the start of the academic year")
        rec = self.recommend()
        self.assertEqual(rec.outcome, "CORRECTIONS_REQUIRED")
        codes = set(self.codes(rec))
        self.assertIn("DEFICIENCY_OPEN", codes)
        self.assertIn("SOURCE_UNAVAILABLE", codes)       # primary outcome is corrections; the rest is still listed
        self.assertEqual(rec.institution_actions, 1)

    def test_missing_required_document_means_corrections(self):
        self.craft(skip_docs=("building_stability",), outcomes={"DOC.BUILDING.PRESENT": "FAIL"})
        self.finding("RULE:DOC.BUILDING.PRESENT", rule_id="DOC.BUILDING.PRESENT", severity="DEFICIENCY", owner="INSTITUTION",
                     fix_doc_type="building_stability")
        rec = self.recommend()
        self.assertEqual(rec.outcome, "CORRECTIONS_REQUIRED")
        self.assertEqual(self.codes(rec).count("MISSING_DOCUMENT"), 1)

    def test_an_officer_owned_deficiency_is_not_a_correction_for_the_institution(self):
        self.craft(outcomes={"INTAKE.LETTER_VS_RECORD": "FAIL"})
        self.finding("RULE:INTAKE.LETTER_VS_RECORD", rule_id="INTAKE.LETTER_VS_RECORD", severity="DEFICIENCY", owner="OFFICER")
        self.assertEqual(self.recommend().outcome, "OFFICER_REVIEW_REQUIRED")

    def test_documents_still_processing_are_uncertain(self):
        self.craft()
        with transaction() as c:
            c.execute("UPDATE documents SET processing_state='PROCESSING' WHERE doc_type='affidavit'")
        rec = self.recommend()
        self.assertEqual((rec.outcome, self.codes(rec)), ("OFFICER_REVIEW_REQUIRED", ["PROCESSING_INCOMPLETE"]))

    def test_an_application_nothing_has_been_checked_for_needs_uploads_first(self):
        rec = self.recommend()
        self.assertEqual(rec.outcome, "CORRECTIONS_REQUIRED")
        self.assertIn("NOT_VALIDATED_YET", self.codes(rec))
        self.assertEqual(self.codes(rec).count("MISSING_DOCUMENT"), 5)
        self.assertNotIn("RULE_NOT_EVALUATED", self.codes(rec))

    def test_only_three_outcomes_exist(self):
        self.craft()
        self.assertIn(self.recommend().outcome, OUTCOMES)
        from app.schemas_ai import RoutingOut
        self.assertEqual(set(RoutingOut.model_fields["outcome"].annotation.__args__), OUTCOMES)


class ActionTests(Crafted):
    def run_step(self, job_id="job-x"):
        with transaction() as c:
            c.execute("INSERT OR IGNORE INTO jobs (id, application_id, kind, state, stage, progress, created_at, updated_at)"
                      " VALUES (?, 'app', 'VALIDATE', 'RUNNING', 'x', 0, ?, ?)", (job_id, now_iso(), now_iso()))
            app = dict(c.execute("SELECT * FROM applications WHERE id='app'").fetchone())
            routing.routing_step(c, job_id, app, lambda code, text, progress: self.stages.append((code, text, progress)))
            c.execute("UPDATE jobs SET state='DONE' WHERE id=?", (job_id,))

    def setUp(self):
        super().setUp()
        self.stages: list[tuple] = []

    def notes(self, kind):
        with reader() as c:
            return [dict(r) for r in c.execute("SELECT * FROM notifications WHERE kind=? ORDER BY created_at", (kind,))]

    def test_corrections_notify_the_institution_once_and_every_action_is_audited(self):
        self.craft(outcomes={"FIRE.VALID": "FAIL"})
        self.finding("RULE:FIRE.VALID", rule_id="FIRE.VALID", severity="DEFICIENCY", owner="INSTITUTION", fix_doc_type="fire_noc")
        self.run_step()
        self.assertEqual(self.stages, [("ROUTING", "Recommending next steps", 95)])
        sent = self.notes("CORRECTIONS_REQUIRED")
        self.assertEqual(len(sent), 1)
        self.assertEqual((sent[0]["user_id"], sent[0]["link"], sent[0]["application_id"]), ("usr", "/applications/app", "app"))
        with reader() as c:
            actions = [json.loads(r["payload_json"]) for r in c.execute("SELECT * FROM audit_events WHERE action='routing.action'")]
            stored = c.execute("SELECT * FROM routing_recommendations").fetchone()
        self.assertIn("NOTIFY_INSTITUTION", {a["action"] for a in actions})
        self.assertTrue(all(a["outcome"] == "CORRECTIONS_REQUIRED" and a["run_id"] == self.run_id for a in actions))
        self.assertEqual((stored["outcome"], stored["policy_version"], stored["ai_used"]), ("CORRECTIONS_REQUIRED", routing.POLICY_VERSION, 0))
        self.run_step("job-y")   # same state again: no second notification, no second row for the same run
        self.assertEqual(len(self.notes("CORRECTIONS_REQUIRED")), 1)
        with reader() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM routing_recommendations").fetchone()[0], 1)
        with reader() as c:
            current = routing.current(c, "app")
        self.assertEqual(current["outcome"], "CORRECTIONS_REQUIRED")
        self.assertIn("NOTIFY_INSTITUTION", {a["type"] for a in current["automated_actions"]})

    def test_uncertain_items_are_escalated_to_officers_with_a_link(self):
        self.craft(simulated=True)
        self.run_step()
        sent = self.notes("OFFICER_NEEDED")
        self.assertEqual(len(sent), 1)
        self.assertEqual((sent[0]["user_id"], sent[0]["link"]), ("off", "/applications/app"))
        self.assertEqual(self.notes("CORRECTIONS_REQUIRED"), [])
        with reader() as c:
            actions = {json.loads(r["payload_json"])["action"] for r in c.execute("SELECT * FROM audit_events WHERE action='routing.action'")}
        self.assertIn("ESCALATE_TO_OFFICERS", actions)

    def test_a_case_without_open_findings_is_marked_for_queue_ordering(self):
        self.craft()
        self.run_step()
        with reader() as c:
            stored = c.execute("SELECT * FROM routing_recommendations").fetchone()
            payloads = [json.loads(r["payload_json"]) for r in c.execute("SELECT * FROM audit_events WHERE action='routing.action'")]
        self.assertEqual((stored["outcome"], stored["queue_flag"]), ("READY_FOR_SCRUTINY", "NO_OPEN_FINDINGS"))
        self.assertEqual([p["action"] for p in payloads], ["MARK_NO_OPEN_FINDINGS"])
        self.assertEqual(self.notes("CORRECTIONS_REQUIRED") + self.notes("OFFICER_NEEDED"), [])

    def test_no_notifications_while_other_documents_are_still_processing(self):
        self.craft(outcomes={"FIRE.VALID": "FAIL"})
        self.finding("RULE:FIRE.VALID", rule_id="FIRE.VALID", severity="DEFICIENCY", owner="INSTITUTION", fix_doc_type="fire_noc")
        with transaction() as c:
            c.execute("INSERT INTO jobs (id, application_id, kind, state, stage, progress, created_at, updated_at)"
                      " VALUES ('job-other','app','PROCESS_DOCUMENT','QUEUED','Queued',0,?,?)", (now_iso(), now_iso()))
        self.run_step()
        self.assertEqual(self.notes("CORRECTIONS_REQUIRED"), [])
        with reader() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM routing_recommendations").fetchone()[0], 1)
        with transaction() as c:
            c.execute("UPDATE jobs SET state='DONE' WHERE id='job-other'")
        self.run_step("job-z")
        self.assertEqual(len(self.notes("CORRECTIONS_REQUIRED")), 1)

    def test_an_unread_notice_is_not_repeated_for_every_upload(self):
        self.craft(outcomes={"FIRE.VALID": "FAIL"})
        self.finding("RULE:FIRE.VALID", rule_id="FIRE.VALID", severity="DEFICIENCY", owner="INSTITUTION", fix_doc_type="fire_noc")
        self.run_step()
        self.finding("RULE:AY.AFFIDAVIT", rule_id="AY.AFFIDAVIT", severity="DEFICIENCY", owner="INSTITUTION", fix_doc_type="affidavit")
        self.run_step("job-b")      # the picture changed, but the first notice is still unread
        self.assertEqual(len(self.notes("CORRECTIONS_REQUIRED")), 1)

    def test_a_failure_inside_routing_never_fails_the_job_or_loses_the_findings(self):
        self.craft()
        with transaction() as c:
            c.execute("DROP TABLE routing_recommendations")
        self.run_step()       # must not raise
        with reader() as c:
            self.assertEqual(c.execute("SELECT text FROM job_notes").fetchone()[0], "Routing recommendation skipped: error")


class PipelineGuaranteeTests(AICase):
    """Real documents through the real pipeline: a case with a planted fault is never READY."""
    env_extra = {"AI_PROVIDER": "none"}

    def test_planted_faults_are_never_ready(self):
        from datetime import date
        from synthetic import generator as g
        inst = g.Inst("Synthetic institute", "1-SYN-TEST")
        bundle = {
            "affidavit": g.affidavit(inst, "2026-27", 300, 60, date(2026, 1, 7)),
            "faculty_summary": g.faculty_summary(inst, "2026-27", 60, 1200, 240),                        # intake differs
            "fire_noc": g.certificate("fire_noc", inst, "FNOC/SYN/AI/1", date(2024, 4, 1), date(2026, 3, 31)),   # expired
        }
        for doc_type, pdf in bundle.items():
            self.upload(doc_type, f"{doc_type}.pdf", pdf)
        with reader() as c:
            rec = routing.compute(c, "app")
        self.assertEqual(rec.outcome, "CORRECTIONS_REQUIRED")
        self.assertNotEqual(rec.outcome, "READY_FOR_SCRUTINY")
        with reader() as c:
            stored = c.execute("SELECT outcome FROM routing_recommendations ORDER BY computed_at DESC, rowid DESC").fetchone()
        self.assertEqual(stored["outcome"], "CORRECTIONS_REQUIRED")


class RoutingApiTests(CoreApiCase):
    def routing(self, session, name):
        return session.get(f"{self.base}/applications/{self.app_id(session, name)}/routing")

    def test_every_seeded_case_gets_one_of_three_outcomes_and_none_is_ready(self):
        officer = self.session("officer@aicte.synthetic.in")
        seen = {}
        for name in ("Shakti Institute", "Godavari", "Krishna", "Shakti Women"):
            r = self.routing(officer, name)
            self.assertEqual(r.status_code, 200, r.text)
            body = r.json()
            self.assertIn(body["outcome"], OUTCOMES)
            self.assertTrue(body["reasons"])
            self.assertEqual(set(body), {"outcome", "reasons", "automated_actions", "run_id", "computed_at", "ai_used", "policy_version"})
            seen[name] = body
        self.assertEqual(seen["Godavari"]["outcome"], "CORRECTIONS_REQUIRED")
        # the clean look-alikes still have simulated-only sources, so a person confirms them
        self.assertEqual(seen["Shakti Institute"]["outcome"], "OFFICER_REVIEW_REQUIRED")
        self.assertIn("SIMULATED_SOURCE_ONLY", {r["code"] for r in seen["Shakti Institute"]["reasons"]})
        self.assertFalse(any(b["outcome"] == "READY_FOR_SCRUTINY" for b in seen.values()))

    def test_authorization(self):
        officer = self.session("officer@aicte.synthetic.in")
        godavari = self.app_id(officer, "Godavari")
        self.assertEqual(self.client.get(f"{self.base}/applications/{godavari}/routing").status_code, 401)
        other = self.session("nodal@shakti.synthetic.in")
        self.assertEqual(other.get(f"{self.base}/applications/{godavari}/routing").status_code, 404)
        own = self.session("nodal@godavari.synthetic.in")
        r = own.get(f"{self.base}/applications/{godavari}/routing")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("matched_", r.text)
        self.assertEqual(self.session("auditor@aicte.synthetic.in").get(f"{self.base}/applications/{godavari}/routing").status_code, 200)

    def test_an_officer_can_clear_an_ai_suggestion_and_only_an_officer(self):
        officer = self.session("officer@aicte.synthetic.in")
        shakti = self.app_id(officer, "Shakti Institute")
        doc = next(d for d in officer.get(f"{self.base}/applications/{shakti}").json()["documents"] if d["doc_type"] == "fire_noc")["id"]
        with self.sql() as db:
            db.execute("INSERT INTO ai_suggestions (id, document_id, application_id, field, value, page, quote, reason, model,"
                       " status, created_at) VALUES ('sug-api', ?, ?, 'valid_to', '31-12-2099', 1, NULL, 'conflicts_with_page',"
                       " 'm', 'OPEN', '2026-10-23T00:00:00+00:00')", (doc, shakti))
        evidence = officer.get(f"{self.base}/documents/{doc}/evidence").json()
        self.assertEqual([(s["field"], s["reason"]) for s in evidence["ai_suggestions"]], [("valid_to", "conflicts_with_page")])
        self.assertIn("AI_SUGGESTION_UNCONFIRMED", {r["code"] for r in self.routing(officer, "Shakti Institute").json()["reasons"]})
        url = f"{self.base}/documents/{doc}/ai-suggestions/review"
        body = {"field": "valid_to", "decision": "DISMISS", "reason": "Checked the page; the date is as printed."}
        self.assertEqual(self.client.post(url, json=body).status_code, 401)
        self.assertEqual(self.session("nodal@shakti.synthetic.in").post(url, json=body).status_code, 403)
        self.assertEqual(self.session("auditor@aicte.synthetic.in").post(url, json=body).status_code, 403)
        self.assertEqual(officer.post(url, json={**body, "reason": "short"}).status_code, 422)
        self.assertEqual(officer.post(url, json={**body, "field": "total_intake"}).status_code, 404)
        self.assertEqual(officer.post(url, json=body).status_code, 200)
        self.assertEqual(officer.post(url, json=body).status_code, 404)    # nothing open any more
        self.assertEqual(officer.get(f"{self.base}/documents/{doc}/evidence").json()["ai_suggestions"], [])
        self.assertNotIn("AI_SUGGESTION_UNCONFIRMED", {r["code"] for r in self.routing(officer, "Shakti Institute").json()["reasons"]})
        events = self.session("auditor@aicte.synthetic.in").get(f"{self.base}/audit?limit=200").json()
        self.assertIn("ai.suggestion_dismiss", {e["action"] for e in events})
        self.assertNotIn("Checked the page", json.dumps(events))     # only a hash of the reason is audited


if __name__ == "__main__":
    unittest.main()
