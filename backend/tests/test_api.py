"""End-to-end API tests against a real server process on a freshly seeded, synthetic database."""
from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import requests

BACKEND = Path(__file__).resolve().parents[1]
PASSWORD = "test-password-123"


_TEMPLATE: tempfile.TemporaryDirectory | None = None


def setUpModule():
    """Seed once; each test class gets its own copy so classes cannot affect each other."""
    global _TEMPLATE
    _TEMPLATE = tempfile.TemporaryDirectory()
    env = {**os.environ, "DATA_DIR": _TEMPLATE.name, "SEED_DEMO_PASSWORD": PASSWORD}
    subprocess.run([sys.executable, "-m", "synthetic.seed"], cwd=BACKEND, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def tearDownModule():
    if _TEMPLATE:
        _TEMPLATE.cleanup()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ApiTestCase(unittest.TestCase):
    proc: subprocess.Popen
    base: str
    tmp: tempfile.TemporaryDirectory

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        shutil.copytree(_TEMPLATE.name, cls.tmp.name, dirs_exist_ok=True)
        env = {**os.environ, "DATA_DIR": cls.tmp.name, "WORKER_THREADS": "1",
               "LOGIN_RATE_PER_MINUTE": "1000", "UPLOAD_RATE_PER_MINUTE": "1000", "APP_ENV": "test"}
        port = _free_port()
        cls.base = f"http://127.0.0.1:{port}/api/v1"
        cls.log = open(Path(cls.tmp.name) / "server.log", "w")
        cls.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)], cwd=BACKEND,
                                    env=env, stdout=cls.log, stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                if requests.get(cls.base + "/health", timeout=1).ok:
                    break
            except requests.ConnectionError:
                time.sleep(0.1)
        cls.db = Path(cls.tmp.name) / "pramaan.sqlite3"
        cls.demo = Path(cls.tmp.name) / "demo_files"

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(10)
        cls.log.close()
        cls.tmp.cleanup()

    def session(self, email: str) -> requests.Session:
        s = requests.Session()
        s.headers["X-Requested-With"] = "pramaan"
        r = s.post(self.base + "/auth/login", json={"email": email, "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)
        return s

    def wait_job(self, s: requests.Session, job_id: str, timeout: float = 60) -> dict:
        end = time.time() + timeout
        while time.time() < end:
            job = s.get(f"{self.base}/jobs/{job_id}").json()
            if job["state"] in ("DONE", "FAILED"):
                return job
            time.sleep(0.2)
        self.fail("job did not finish")

    def app_id(self, s: requests.Session, name_part: str) -> str:
        return next(a["id"] for a in s.get(self.base + "/applications").json() if name_part in a["institution"]["name"])


class AuthAndAccessTests(ApiTestCase):
    def test_login_rejects_bad_password_generically(self):
        r = requests.post(self.base + "/auth/login", json={"email": "officer@aicte.synthetic.in", "password": "nope"})
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (401, "invalid_credentials"))
        r2 = requests.post(self.base + "/auth/login", json={"email": "nobody@x.in", "password": "nope"})
        self.assertEqual(r2.json()["error"]["message"], r.json()["error"]["message"])

    def test_session_cookie_flags(self):
        r = requests.post(self.base + "/auth/login", json={"email": "officer@aicte.synthetic.in", "password": PASSWORD})
        cookie = r.headers["set-cookie"].lower()
        for flag in ("httponly", "samesite=strict", "path=/"):
            self.assertIn(flag, cookie)

    def test_unauthenticated_and_csrf(self):
        self.assertEqual(requests.get(self.base + "/applications").status_code, 401)
        s = self.session("nodal@deccan.synthetic.in")
        del s.headers["X-Requested-With"]
        r = s.post(self.base + "/applications", json={"category": "EOA_EXISTING", "academic_year": "2026-27"})
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "csrf"))

    def test_institution_cannot_see_other_institution(self):
        officer = self.session("officer@aicte.synthetic.in")
        godavari = self.app_id(officer, "Godavari")
        inst = self.session("nodal@shakti.synthetic.in")
        self.assertEqual(inst.get(f"{self.base}/applications/{godavari}").status_code, 404)
        self.assertEqual(inst.get(f"{self.base}/applications/{godavari}/findings").status_code, 404)
        doc = officer.get(f"{self.base}/applications/{godavari}").json()["documents"][0]["id"]
        self.assertEqual(inst.get(f"{self.base}/documents/{doc}/pages/1").status_code, 404)
        self.assertEqual(requests.get(f"{self.base}/documents/{doc}/pages/1").status_code, 401)

    def test_role_checks(self):
        auditor = self.session("auditor@aicte.synthetic.in")
        fid = auditor.get(f"{self.base}/applications/{self.app_id(auditor, 'Godavari')}/findings").json()[0]["id"]
        r = auditor.post(f"{self.base}/findings/{fid}/review", json={"decision": "DISMISS", "reason": "auditor should not"})
        self.assertEqual(r.status_code, 403)
        inst = self.session("nodal@shakti.synthetic.in")
        self.assertEqual(inst.get(self.base + "/audit").status_code, 403)

    def test_security_headers(self):
        r = requests.get(self.base + "/health")
        for h in ("content-security-policy", "x-content-type-options", "x-frame-options", "referrer-policy"):
            self.assertIn(h, r.headers)
        self.assertEqual(r.headers["cache-control"], "no-store")


class SeededScenarioTests(ApiTestCase):
    def findings(self, s, name):
        return s.get(f"{self.base}/applications/{self.app_id(s, name)}/findings").json()

    def test_clean_and_hard_negative_bundles_have_no_findings(self):
        s = self.session("officer@aicte.synthetic.in")
        for name in ("Shakti Institute", "Shakti Women"):  # reprinted letter; same-trust shared photograph
            with self.subTest(name=name):
                self.assertEqual(self.findings(s, name), [])

    def test_planted_defects_are_found_with_evidence(self):
        s = self.session("officer@aicte.synthetic.in")
        f = {x["rule_id"] or x["source_kind"]: x for x in self.findings(s, "Godavari")}
        self.assertEqual(set(f), {"DOC.BUILDING.PRESENT", "INTAKE.NO_CHANGE", "FIRE.VALID", "INTAKE.CONSISTENT",
                                  "FACULTY.CONSISTENT", "INTEGRITY", "DUPLICATE"})
        self.assertTrue(all(x["advisory"] for x in f.values()))
        ev = f["INTAKE.CONSISTENT"]["evidence"]
        self.assertEqual({e["doc_type"] for e in ev}, {"affidavit", "faculty_summary"})
        self.assertTrue(all(len(e["bbox"]) == 4 and e["page"] == 1 for e in ev))
        self.assertIn("indicator that requires verification", f["INTEGRITY"]["explanation"])
        self.assertNotIn("forged", " ".join(x["explanation"].lower() for x in f.values()))

    def test_verification_ladder_statuses(self):
        s = self.session("officer@aicte.synthetic.in")
        vers = s.get(f"{self.base}/applications/{self.app_id(s, 'Krishna')}/verifications").json()
        by = {(v["channel"], v["status"]) for v in vers}
        self.assertIn(("signed_qr", "MISMATCH_DETECTED"), by)
        self.assertIn(("issuer_registry", "SOURCE_UNAVAILABLE"), by)
        self.assertIn(("aicte_records", "MISMATCH_DETECTED"), by)
        self.assertTrue(all(v["simulated"] for v in vers if v["channel"] in ("issuer_registry", "aicte_records")))
        self.assertFalse(any(v["simulated"] for v in vers if v["channel"] == "signed_qr"))

    def test_institution_sees_duplicate_without_other_institution_details(self):
        s = self.session("nodal@godavari.synthetic.in")
        dup = next(x for x in self.findings(s, "Godavari") if x["source_kind"] == "DUPLICATE")
        self.assertFalse(any(k.startswith("matched_") for k in dup["proof"]))
        other = [e for e in dup["evidence"] if e.get("other_application")][0]
        self.assertNotIn("document_id", {k for k, v in other.items() if v})


class WorkflowTests(ApiTestCase):
    def test_full_institution_to_officer_loop(self):
        inst = self.session("nodal@deccan.synthetic.in")
        r = inst.post(self.base + "/applications", json={"category": "EOA_EXISTING", "academic_year": "2026-27"})
        self.assertEqual(r.status_code, 201, r.text)
        app_id = r.json()["id"]
        files = {"eoa_letter": "D_EoA_2025-26.pdf", "affidavit": "D_Affidavit_2026-27.pdf",
                 "fire_noc": "D_Fire_NOC_EXPIRED.pdf", "building_stability": "D_Structural_Stability.pdf",
                 "faculty_summary": "D_Faculty_Summary_WRONG_INTAKE.pdf", "infra_photo": "D_Lab_Photo.png"}
        for doc_type, name in files.items():
            with open(self.demo / name, "rb") as fh:
                r = inst.post(f"{self.base}/applications/{app_id}/documents", data={"doc_type": doc_type},
                              files={"file": (name, fh, "application/octet-stream")})
            self.assertEqual(r.status_code, 202, r.text)
            self.assertEqual(self.wait_job(inst, r.json()["job"]["id"])["state"], "DONE")
        open_rules = {f["rule_id"] for f in inst.get(f"{self.base}/applications/{app_id}/findings").json()}
        self.assertEqual(open_rules, {"FIRE.VALID", "INTAKE.CONSISTENT"})
        plan = inst.get(f"{self.base}/applications/{app_id}/repair-plan").json()
        self.assertEqual({a["doc_type"] for a in plan["institution_actions"]}, {"fire_noc", "faculty_summary"})

        # Repair: upload the renewed NOC; only rules reading fire_noc (plus completeness) re-run.
        with open(self.demo / "D_Fire_NOC_RENEWED.pdf", "rb") as fh:
            r = inst.post(f"{self.base}/applications/{app_id}/documents", data={"doc_type": "fire_noc"},
                          files={"file": ("renewed.pdf", fh, "application/pdf")})
        self.wait_job(inst, r.json()["job"]["id"])
        runs = inst.get(f"{self.base}/applications/{app_id}/runs").json()
        self.assertIn("FIRE.VALID", runs[0]["affected_rules"])
        self.assertNotIn("INTAKE.CONSISTENT", runs[0]["affected_rules"])
        self.assertEqual(runs[0]["summary"]["resolved"], 1)
        all_f = inst.get(f"{self.base}/applications/{app_id}/findings?include_resolved=true").json()
        self.assertEqual({f["rule_id"]: f["state"] for f in all_f}["FIRE.VALID"], "RESOLVED")

        r = inst.post(f"{self.base}/applications/{app_id}/submit")
        self.assertEqual(r.status_code, 200, r.text)

        officer = self.session("officer@aicte.synthetic.in")
        f = officer.get(f"{self.base}/applications/{app_id}/findings").json()[0]
        r = officer.post(f"{self.base}/findings/{f['id']}/review", json={"decision": "REQUEST_CLARIFICATION", "reason": "short"})
        self.assertEqual(r.status_code, 422)
        r = officer.post(f"{self.base}/findings/{f['id']}/review",
                         json={"decision": "REQUEST_CLARIFICATION", "reason": "Ask which intake figure is correct."})
        self.assertEqual((r.status_code, r.json()["state"]), (200, "CLARIFICATION_REQUESTED"))
        events = officer.get(f"{self.base}/audit?application_id={app_id}").json()
        self.assertIn("finding.request_clarification", {e["action"] for e in events})

    def test_upload_rejections(self):
        inst = self.session("nodal@shakti.synthetic.in")
        app_id = inst.get(self.base + "/applications").json()[0]["id"]
        url = f"{self.base}/applications/{app_id}/documents"
        cases = [("affidavit", ("x.pdf", b"MZ\x90 executable", "application/pdf"), "unsupported_type"),
                 ("affidavit", ("photo.pdf", (self.demo / "D_Lab_Photo.png").read_bytes(), "application/pdf"), "wrong_type"),
                 ("nonsense", ("a.pdf", b"%PDF-1.4", "application/pdf"), "validation_error"),
                 ("affidavit", ("../../etc/passwd.pdf", b"%PDF-1.4 broken", "application/pdf"), "malformed_pdf")]
        for doc_type, file, code in cases:
            with self.subTest(code=code):
                r = inst.post(url, data={"doc_type": doc_type}, files={"file": file})
                self.assertEqual((r.status_code, r.json()["error"]["code"]), (422, code))
        big = b"%PDF-1.4\n" + b"0" * (11 * 1024 * 1024)
        r = inst.post(url, data={"doc_type": "affidavit"}, files={"file": ("big.pdf", big, "application/pdf")})
        self.assertEqual(r.status_code, 413)


class GovernanceTests(ApiTestCase):
    def test_four_eyes_rule_activation(self):
        a1, a2 = self.session("admin@aicte.synthetic.in"), self.session("admin2@aicte.synthetic.in")
        r = a1.post(self.base + "/rules/proposals", json={"changes": {"FACULTY.RATIO": {"max_ratio": 15}},
                                                          "note": "Tighten ratio for test scenario"})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["diff"], [{"rule_id": "FACULTY.RATIO", "param": "max_ratio", "old": 20, "new": 15}])
        vid = r.json()["version"]["id"]
        self.assertEqual(a1.post(f"{self.base}/rules/versions/{vid}/activate").status_code, 403)
        r = a2.post(f"{self.base}/rules/versions/{vid}/activate")
        self.assertEqual((r.status_code, r.json()["status"]), (200, "ACTIVE"))
        self.assertEqual(a2.get(self.base + "/rules").json()["version"]["version"], "2026.2")
        bad = a1.post(self.base + "/rules/proposals", json={"changes": {"FACULTY.RATIO": {"evil": 1}}, "note": "unknown param"})
        self.assertEqual(bad.status_code, 422)

    def test_audit_chain_detects_database_tampering(self):
        auditor = self.session("auditor@aicte.synthetic.in")
        self.assertTrue(auditor.get(self.base + "/audit/verify").json()["valid"])
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE audit_events SET action = 'tampered' WHERE seq = 5")
        r = auditor.get(self.base + "/audit/verify").json()
        self.assertEqual((r["valid"], r["first_broken_seq"]), (False, 5))


if __name__ == "__main__":
    unittest.main()
