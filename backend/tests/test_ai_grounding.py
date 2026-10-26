"""A proposal becomes a claim only when it is found on the page, printed as that field."""
from __future__ import annotations

import unittest
from datetime import date

from app.ai import ground
from app.db import reader, transaction
from app.pipeline import extract
from app.pipeline.ai_extract import _integrate, rule_fields
from app.rulepacks import active_version
from synthetic import generator as g
from synthetic import variants as v
from tests.ai_support import PID, AICase, fixture, FakeTransport  # noqa: F401

INST = g.Inst("Synthetic institute", PID)


def pages_of(pdf: bytes) -> dict[int, ground.PageData]:
    return ground.pages_from(extract.extract_pdf(pdf))


class GroundingUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expiry = v.fire_noc_variant("expiry_label", INST, "FNOC/SYN/AI/0001", date(2025, 4, 1), date(2027, 3, 31))
        cls.table = v.fire_noc_variant("two_column", INST, "FNOC/SYN/AI/0003", date(2025, 4, 1), date(2027, 3, 31))
        cls.expiry_pages = pages_of(cls.expiry)
        cls.table_pages = pages_of(cls.table)

    def test_found_on_page_gives_a_claim_with_the_real_box(self):
        result = ground.ground("valid_to", "date", "31-03-2027", 1, "Expiry Date: 31-03-2027", self.expiry_pages)
        claim = result.claim
        self.assertIsNotNone(claim)
        word = next(w for w in self.expiry_pages[1].flat if w.text == "31-03-2027")
        self.assertEqual(claim.bbox, (word.x0, word.top, word.x1, word.bottom))
        self.assertEqual((claim.extractor, claim.page, claim.value_norm), ("ai+text", 1, "2027-03-31"))
        self.assertEqual(claim.confidence, extract.TEXT_LAYER_CONFIDENCE)
        self.assertEqual((claim.page_width, claim.page_height), (self.expiry_pages[1].width, self.expiry_pages[1].height))

    def test_no_quote_lowers_confidence(self):
        with_quote = ground.ground("valid_to", "date", "31-03-2027", 1, "Expiry Date: 31-03-2027", self.expiry_pages)
        without = ground.ground("valid_to", "date", "31-03-2027", 1, None, self.expiry_pages)
        self.assertLess(without.claim.confidence, with_quote.claim.confidence)

    def test_not_found_is_a_reason_not_a_claim(self):
        self.assertEqual(ground.ground("total_intake", "int", "300", 1, None, self.expiry_pages).reason, "not_found_on_page")
        self.assertEqual(ground.ground("valid_to", "date", "31-03-2027", 2, None, self.expiry_pages).reason, "not_found_on_page")
        self.assertEqual(ground.ground("valid_to", "date", "not a date", 1, None, self.expiry_pages).reason, "not_found_on_page")

    def test_a_value_the_page_contradicts_is_a_conflict(self):
        result = ground.ground("valid_to", "date", "31-03-2030", 1, "Expiry Date: 31-03-2030", self.expiry_pages)
        self.assertEqual((result.claim, result.reason), (None, "conflicts_with_page"))

    def test_value_in_the_wrong_place_is_not_taken(self):
        """01-04-2025 is printed on the page, but as the issue date, not as the validity date."""
        result = ground.ground("valid_to", "date", "01-04-2025", 1, "Issued: 01-04-2025", self.expiry_pages)
        self.assertIsNone(result.claim)

    def test_normalisation_of_dates_digits_case_and_spaces(self):
        cases = [("valid_to", "date", "31 March 2027"), ("valid_to", "date", "31/03/2027"), ("valid_to", "date", "2027-03-31"),
                 ("permanent_id", "id", PID.lower()), ("permanent_id", "id", f" {PID} ")]
        for field, vtype, value in cases:
            with self.subTest(value=value):
                result = ground.ground(field, vtype, value, 1, None, self.expiry_pages)
                self.assertIsNotNone(result.claim, result.reason)
        self.assertEqual(ground.canon("12,000", "int"), "12000")
        self.assertEqual(ground.canon("2026 - 2027", "academic_year"), "2026-27")
        self.assertEqual(ground.canon("Rs.360/-", "int"), None)
        self.assertEqual(ground.canon("360/-", "int"), "360")
        self.assertIsNone(ground.canon("three hundred", "int"))

    def test_two_column_table_form(self):
        """Label and value sit far apart in separate cells; the row still reads as 'label value'."""
        result = ground.ground("valid_to", "date", "31-03-2027", 1, "Valid Upto 31-03-2027", self.table_pages)
        self.assertEqual(result.claim.value_norm, "2027-03-31")

    def test_quote_that_does_not_contain_the_value_is_a_conflict(self):
        result = ground.ground("valid_to", "date", "31-03-2027", 1, "Certificate No.: FNOC/SYN/AI/0001", self.expiry_pages)
        self.assertEqual((result.claim, result.reason), (None, "conflicts_with_page"))


class IntegrationTests(AICase):
    """Pipeline-level behaviour with the network seam faked."""

    def test_ai_fills_a_field_the_template_missed_and_reports_the_stage(self):
        pdf = v.fire_noc_variant("expiry_label", INST, "FNOC/SYN/AI/0001", date(2025, 4, 1), date(2027, 3, 31))
        with self.network(lambda call: fixture("extract_noc_expiry")) as net:
            doc = self.upload("fire_noc", "noc.pdf", pdf)
        self.assertEqual(len(net.of("extract")), 1)
        claim = self.claims(doc)["valid_to"]
        self.assertEqual((claim["extractor"], claim["value_norm"], claim["confidence"]), ("ai+text", "2027-03-31", 0.98))
        self.assertGreater(claim["x1"], claim["x0"])
        self.assertEqual(self.suggestions(doc), [])
        with reader() as c:
            stages = {r["stage_code"] for r in c.execute("SELECT stage_code FROM job_stage_durations")}
            self.assertIn("AI_EXTRACTION", stages)
            self.assertIn("ai.extraction", self.audit_actions())
            fire_valid = c.execute("SELECT outcome FROM rule_results WHERE rule_id='FIRE.VALID' ORDER BY rowid DESC").fetchone()
        self.assertEqual(fire_valid["outcome"], "PASS")

    def test_no_trigger_means_no_call(self):
        plain = g.certificate("fire_noc", INST, "FNOC/SYN/AI/0009", date(2025, 4, 1), date(2027, 3, 31))
        with self.network(lambda call: fixture("explain_new_fact")) as net:
            self.upload("fire_noc", "noc.pdf", plain)
        self.assertEqual((net.of("extract"), net.of("classify")), ([], []))   # nothing needed the AI to read it

    def test_wrong_values_for_confident_claims_become_suggestions_only(self):
        """A scanned affidavit is read by OCR (0.96); a model that disagrees cannot overwrite it."""
        scan = g.rasterize(g.affidavit(INST, "2026-27", 240, 60, date(2026, 1, 7)))
        wrong = fixture("extract_hostile_aff_honest")
        import json
        body = json.loads(wrong["steps"][0]["content"][0]["text"])
        body["total_intake"] = {"value": "241", "page": 1, "quote": "Total Intake Sought: 241"}
        from tests.ai_support import gemini_body
        with self.network(lambda call: gemini_body(body)):
            doc = self.upload("affidavit", "aff.pdf", scan)
        claims = self.claims(doc)
        self.assertEqual((claims["total_intake"]["value_norm"], claims["total_intake"]["extractor"]), ("240", "ocr+template"))
        self.assertEqual([(s["field"], s["reason"]) for s in self.suggestions(doc)], [("total_intake", "conflicts_with_page")])

    def test_integrate_never_overwrites_a_confident_claim(self):
        pdf = g.certificate("fire_noc", INST, "FNOC/SYN/AI/0010", date(2025, 4, 1), date(2027, 3, 31))
        doc_id = self.upload("fire_noc", "noc.pdf", pdf)
        with reader() as c:
            doc = dict(c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone())
            _, pack = active_version(c)
        fields = rule_fields(pack, "fire_noc")
        pages = pages_of(pdf)
        before = self.claims(doc_id)
        self.assertGreaterEqual(before["valid_to"]["confidence"], 0.95)
        from app.ai.types import FieldProposal
        proposals = {"valid_to": FieldProposal(value="31-12-2099", page=1, quote="Valid Upto 31-12-2099"),
                     "permanent_id": FieldProposal(value="1-SYN-0000-0000", page=1, quote=None)}
        with transaction() as c:
            created, replaced, suggested = _integrate(c, doc, fields, {"valid_to", "permanent_id"}, proposals, pages, before, "m")
        self.assertEqual((created, replaced, suggested), (0, 0, 2))
        self.assertEqual(self.claims(doc_id), before)
        self.assertEqual({s["reason"] for s in self.suggestions(doc_id)}, {"conflicts_with_page"})


class IntegrityCoverageTests(unittest.TestCase):
    def test_ai_text_claims_get_the_overlay_edit_check(self):
        """The text layer says 48, a raster patch shows 68: a claim made by AI from the text layer must be flagged too."""
        from app.pipeline import integrity
        pdf = g.faculty_summary(INST, "2026-27", 48, 960, 240, faculty_overlay=68)
        pages = pages_of(pdf)
        claim = ground.ground("faculty_count", "int", "48", 1, "Number of Regular Faculty: 48", pages).claim
        self.assertEqual(claim.extractor, "ai+text")
        extracted = extract.ExtractedClaim(claim.field, claim.value_raw, claim.value_norm, claim.value_type, claim.page,
                                           claim.bbox, claim.page_width, claim.page_height, claim.extractor, claim.confidence)
        indicators, _ = integrity.visible_text_indicators(pdf, [extracted])
        self.assertEqual([i.kind for i in indicators], ["VISIBLE_TEXT_MISMATCH"])


if __name__ == "__main__":
    unittest.main()
