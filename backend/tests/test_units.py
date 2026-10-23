"""Unit tests: expression safety, rule engine outcomes, audit chain, planner, intake and integrity checks."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline import extract, integrity, safe_expr  # noqa: E402
from app.pipeline.intake import IntakeError, validate_upload  # noqa: E402
from app.pipeline.repair import build_plan  # noqa: E402
from app.pipeline.rules_engine import EvalContext, RulePack, evaluate  # noqa: E402
from app import schemas  # noqa: E402
from synthetic import generator as g  # noqa: E402

PACK_TEXT = (Path(__file__).resolve().parents[1] / "rulepacks/aicte-eoa/2026.1.yaml").read_text()


class SafeExpressionTests(unittest.TestCase):
    def test_arithmetic_and_comparison(self):
        self.assertTrue(safe_expr.evaluate("a / b <= 20 and a > 0", {"a": 1440, "b": 72}))
        self.assertFalse(safe_expr.evaluate("a == b", {"a": "2025-26", "b": "2026-27"}))
        self.assertEqual(safe_expr.evaluate("days_between(x, y)", {"x": date(2026, 1, 1), "y": date(2026, 1, 31)}), 30)

    def test_rejects_dangerous_syntax(self):
        for expr in ["__import__('os')", "a.__class__", "a[0]", "(lambda: 1)()", "[x for x in a]", "a ** 99999999",
                     "open('x')", "a if b else c.d", "x := 1"]:
            with self.subTest(expr=expr):
                with self.assertRaises(safe_expr.ExpressionError):
                    safe_expr.evaluate(expr, {"a": 1, "b": 2, "c": 3})

    def test_rejects_unknown_names_and_long_input(self):
        with self.assertRaises(safe_expr.ExpressionError):
            safe_expr.evaluate("unknown > 1", {"a": 1})
        with self.assertRaises(safe_expr.ExpressionError):
            safe_expr.evaluate("1 + " * 200 + "1", {})


def _claim(field, raw, norm, vtype, conf=0.98, cid=None):
    return {"id": cid or f"clm_{field}", "field": field, "value_raw": raw, "value_norm": norm, "value_type": vtype,
            "page": 1, "x0": 10, "y0": 10, "x1": 50, "y1": 20, "page_width": 595, "page_height": 842,
            "extractor": "text-layer+template", "confidence": conf}


def _ctx(category="EOA_EXISTING", **overrides):
    pid = "1-SYN-0000-0001"
    docs = {t: {"id": f"doc_{t}", "doc_type": t, "original_name": f"{t}.pdf"}
            for t in ("eoa_letter", "affidavit", "fire_noc", "building_stability", "faculty_summary")}
    claims = {
        "doc_eoa_letter": {"permanent_id": _claim("permanent_id", pid, pid, "id"),
                           "academic_year": _claim("academic_year", "2025-26", "2025-26", "academic_year"),
                           "issue_date": _claim("issue_date", "15-04-2025", "2025-04-15", "date"),
                           "print_date": _claim("print_date", "12 September 2026", "2026-09-12", "date"),
                           "total_intake": _claim("total_intake", "240", "240", "int")},
        "doc_affidavit": {"permanent_id": _claim("permanent_id", pid, pid, "id"),
                          "academic_year": _claim("academic_year", "2026-27", "2026-27", "academic_year"),
                          "total_intake": _claim("total_intake", "240", "240", "int"),
                          "faculty_count": _claim("faculty_count", "60", "60", "int")},
        "doc_fire_noc": {"permanent_id": _claim("permanent_id", pid, pid, "id"),
                         "valid_to": _claim("valid_to", "31-03-2027", "2027-03-31", "date")},
        "doc_building_stability": {"permanent_id": _claim("permanent_id", pid, pid, "id"),
                                   "valid_to": _claim("valid_to", "09-02-2029", "2029-02-09", "date")},
        "doc_faculty_summary": {"permanent_id": _claim("permanent_id", pid, pid, "id"),
                                "academic_year": _claim("academic_year", "2026-27", "2026-27", "academic_year"),
                                "faculty_count": _claim("faculty_count", "60", "60", "int"),
                                "student_strength": _claim("student_strength", "960", "960", "int"),
                                "total_intake": _claim("total_intake", "240", "240", "int")},
    }
    ctx = EvalContext(
        application={"id": "app_1", "category": category, "academic_year": "2026-27"},
        institution={"id": "ins_1", "aicte_permanent_id": pid}, record={"approved_intake": 240},
        docs_by_type=docs, claims_by_doc=claims,
        verification_by_doc={"doc_fire_noc": "VERIFIED", "doc_building_stability": "VERIFIED", "doc_eoa_letter": "VERIFIED"},
    )
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


class RuleEngineTests(unittest.TestCase):
    pack = RulePack.from_yaml(PACK_TEXT)

    def outcomes(self, ctx):
        return {r.rule_id: r for r in evaluate(self.pack, ctx)}

    def test_clean_bundle_passes_everything(self):
        res = self.outcomes(_ctx())
        bad = {k: v.outcome for k, v in res.items() if v.outcome not in ("PASS", "NOT_APPLICABLE")}
        self.assertEqual(bad, {})

    def test_reprinted_letter_does_not_trigger_date_rule(self):
        # print_date (Sept 2026) is outside the previous-cycle window; issue_date is inside. Only issue_date counts.
        self.assertEqual(self.outcomes(_ctx())["EOA.PREVIOUS_CYCLE"].outcome, "PASS")

    def test_expiry_fails_with_typed_valid_to(self):
        ctx = _ctx()
        ctx.claims_by_doc["doc_fire_noc"]["valid_to"] = _claim("valid_to", "31-03-2026", "2026-03-31", "date")
        r = self.outcomes(ctx)["FIRE.VALID"]
        self.assertEqual((r.outcome, r.proof["status"]), ("FAIL", "EXPIRED"))
        self.assertEqual(r.evidence[0]["claim_id"], "clm_valid_to")

    def test_missing_document_fails_completeness_and_abstains_elsewhere(self):
        ctx = _ctx()
        del ctx.docs_by_type["affidavit"]
        res = self.outcomes(ctx)
        self.assertEqual(res["DOC.AFFIDAVIT.PRESENT"].outcome, "FAIL")
        self.assertEqual((res["AY.AFFIDAVIT"].outcome, res["AY.AFFIDAVIT"].reason), ("NOT_EVALUABLE", "missing_document"))

    def test_low_confidence_input_abstains_instead_of_failing(self):
        ctx = _ctx()
        ctx.claims_by_doc["doc_affidavit"]["total_intake"] = _claim("total_intake", "3G0", "360", "int", conf=0.41)
        r = self.outcomes(ctx)["INTAKE.NO_CHANGE"]
        self.assertEqual((r.outcome, r.reason), ("NOT_EVALUABLE", "low_confidence"))

    def test_consistency_reports_conflicting_sources(self):
        ctx = _ctx()
        ctx.claims_by_doc["doc_affidavit"]["total_intake"] = _claim("total_intake", "300", "300", "int")
        r = self.outcomes(ctx)["INTAKE.CONSISTENT"]
        self.assertEqual(r.outcome, "FAIL")
        self.assertEqual(r.proof["conflict"], {"240": ["faculty_summary"], "300": ["affidavit"]})
        self.assertEqual(len(r.evidence), 2)

    def test_category_scoping(self):
        ctx = _ctx(category="EOA_INTAKE_INCREASE")
        ctx.claims_by_doc["doc_affidavit"]["total_intake"] = _claim("total_intake", "300", "300", "int")
        self.assertEqual(self.outcomes(ctx)["INTAKE.NO_CHANGE"].outcome, "NOT_APPLICABLE")

    def test_verification_states(self):
        for status, outcome in [("VERIFIED", "PASS"), ("EXPIRED", "PASS"), ("MISMATCH_DETECTED", "FAIL"),
                                ("SOURCE_UNAVAILABLE", "NOT_EVALUABLE"), ("MANUAL_REVIEW_REQUIRED", "NOT_EVALUABLE")]:
            ctx = _ctx()
            ctx.verification_by_doc["doc_fire_noc"] = status
            with self.subTest(status=status):
                self.assertEqual(self.outcomes(ctx)["VERIFY.FIRE_NOC"].outcome, outcome)

    def test_every_rule_cites_a_clause_and_reads_documents(self):
        for rule in self.pack.rules:
            self.assertTrue(rule.clause.ref)
            self.assertTrue(rule.reads(), rule.id)

    def test_rule_pack_rejects_unsafe_expression(self):
        bad = PACK_TEXT.replace('expr: "faculty > 0 and students / faculty <= max_ratio"', 'expr: "__import__(\'os\')"')
        with self.assertRaises(Exception):
            RulePack.from_yaml(bad)


class AuditChainTests(unittest.TestCase):
    def test_tampering_is_detected(self):
        from app import audit
        with tempfile.TemporaryDirectory() as d:
            conn = sqlite3.connect(os.path.join(d, "a.db"), isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.executescript((Path(__file__).resolve().parents[1] / "migrations/0001_init.sql").read_text())
            for i in range(5):
                audit.record(conn, None, "test.event", "thing", f"t{i}", {"i": i})
            self.assertTrue(audit.verify_chain(conn)["valid"])
            conn.execute("UPDATE audit_events SET payload_json = '{\"i\":99}' WHERE seq = 3")
            r = audit.verify_chain(conn)
            self.assertEqual((r["valid"], r["first_broken_seq"]), (False, 3))
            conn.execute("UPDATE audit_events SET payload_json = '{\"i\":2}' WHERE seq = 3")
            conn.execute("DELETE FROM audit_events WHERE seq = 4")
            self.assertEqual(audit.verify_chain(conn)["first_broken_seq"], 5)
            conn.close()


class PlannerTests(unittest.TestCase):
    def test_groups_by_document_and_links_shared_field(self):
        def f(fid, rule_type, sev, fix, owner="INSTITUTION", fields=()):
            return {"id": fid, "state": "OPEN", "severity": sev, "fix_doc_type": fix, "action_owner": owner,
                    "title": fid, "remedy": f"remedy {fid}", "explanation": "x",
                    "proof": {"rule": {"type": rule_type}},
                    "evidence": [{"doc_type": d, "field": fl} for d, fl in fields]}
        plan = build_plan([
            f("no_change", "assert", "DEFICIENCY", "affidavit", fields=[("affidavit", "total_intake")]),
            f("consistent", "consistency", "REVIEW", None, fields=[("affidavit", "total_intake"), ("faculty_summary", "total_intake")]),
            f("fire", "expiry", "DEFICIENCY", "fire_noc", fields=[("fire_noc", "valid_to")]),
            f("verify", "verification", "REVIEW", "fire_noc", owner="OFFICER"),
        ])
        inst = {a["doc_type"]: a for a in plan["institution_actions"]}
        self.assertEqual(sorted(inst["affidavit"]["resolves"]), ["consistent", "no_change"])
        self.assertTrue(inst["fire_noc"]["title"].startswith("Upload a renewed"))
        self.assertEqual([a["resolves"] for a in plan["officer_actions"]], [["verify"]])


class IntakeTests(unittest.TestCase):
    def test_content_type_is_checked_not_extension(self):
        with self.assertRaises(IntakeError) as e:
            validate_upload(b"MZ\x90\x00 not a pdf", "affidavit", 40)
        self.assertEqual(e.exception.code, "unsupported_type")
        png = g.lab_photo(1)
        with self.assertRaises(IntakeError):
            validate_upload(png, "affidavit", 40)  # image where a PDF is required
        with self.assertRaises(IntakeError):
            validate_upload(b"%PDF-1.7\n garbage", "affidavit", 40)
        self.assertEqual(validate_upload(png, "infra_photo", 40).mime, "image/png")


class IntegrityTests(unittest.TestCase):
    inst = g.Inst("Test Institute (Synthetic)", "1-SYN-9999-0009")

    def test_overlay_edit_is_flagged_and_clean_copy_is_not(self):
        for overlay, expected in [(92, ["VISIBLE_TEXT_MISMATCH"]), (None, [])]:
            pdf = g.faculty_summary(self.inst, "2026-27", 72, 1440, 360, faculty_overlay=overlay)
            res = extract.extract_pdf(pdf)
            claims = extract.extract_claims(res, "faculty_summary")
            found, _ = integrity.visible_text_indicators(pdf, claims)
            with self.subTest(overlay=overlay):
                self.assertEqual([i.kind for i in found], expected)

    def test_incremental_save_is_flagged(self):
        pdf = g.certificate("fire_noc", self.inst, "FNOC/SYN/1/1", date(2025, 1, 1), date(2027, 1, 1))
        self.assertEqual(integrity.structure_indicators(pdf)[0], [])
        kinds = [i.kind for i in integrity.structure_indicators(g.incremental_edit(pdf))[0]]
        self.assertIn("INCREMENTAL_UPDATE", kinds)

    def test_scanned_copy_uses_ocr_with_provenance(self):
        pdf = g.rasterize(g.affidavit(self.inst, "2026-27", 180, 45, date(2026, 1, 12)))
        res = extract.extract_pdf(pdf)
        claims = {c.field: c for c in extract.extract_claims(res, "affidavit")}
        self.assertTrue(res.used_ocr)
        self.assertEqual(claims["total_intake"].value_norm, "180")
        self.assertEqual(claims["total_intake"].extractor, "ocr+template")
        self.assertEqual(len(claims["total_intake"].bbox), 4)


class ContractTests(unittest.TestCase):
    def test_no_adverse_decision_vocabulary(self):
        """The system must not be able to express approve/reject/forged decisions."""
        banned = {"APPROVED", "REJECTED", "FORGED", "FRAUD", "FAKE"}
        for name in ("ApplicationStatus", "VerificationStatus", "FindingState", "ReviewDecision", "RuleOutcome"):
            values = set(getattr(schemas, name).__args__)
            self.assertFalse(values & banned, name)
        self.assertEqual(set(schemas.VerificationStatus.__args__),
                         {"VERIFIED", "MISMATCH_DETECTED", "EXPIRED", "VERIFICATION_PENDING", "SOURCE_UNAVAILABLE",
                          "MANUAL_REVIEW_REQUIRED"})


if __name__ == "__main__":
    unittest.main()
