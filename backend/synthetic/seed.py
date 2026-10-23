"""Create a fully synthetic demo dataset by running real uploads through the real pipeline.

Usage:  python -m synthetic.seed [--reset]

Passwords come from SEED_DEMO_PASSWORD or are generated randomly; they are printed once and written
to DATA_DIR/demo_credentials.txt (mode 600, git-ignored). Nothing here is real data.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
from dataclasses import dataclass
from datetime import date

from app import audit
from app.config import get_settings
from app.db import new_id, now_iso, reader, transaction
from app.pipeline.intake import validate_upload
from app.pipeline.orchestrator import create_job, run_job
from app.security import Principal, hash_password
from app.storage import LocalStorage
from app.main import bootstrap
from synthetic import generator as g


@dataclass
class InstSpec:
    key: str
    name: str
    pid: str
    trust: str
    state: str
    intake: int
    email: str


INSTITUTIONS = [
    InstSpec("A", "Shakti Institute of Technology (Synthetic)", "1-SYN-4417-0001", "Shakti Educational Trust", "Telangana", 360, "nodal@shakti.synthetic.in"),
    InstSpec("B", "Godavari College of Engineering (Synthetic)", "1-SYN-5520-0002", "Godavari Vidya Samiti", "Andhra Pradesh", 240, "nodal@godavari.synthetic.in"),
    InstSpec("C", "Krishna Institute of Engineering (Synthetic)", "1-SYN-6631-0003", "Krishna Education Society", "Karnataka", 180, "nodal@krishna.synthetic.in"),
    InstSpec("D", "Deccan Institute of Technology (Synthetic)", "1-SYN-7742-0004", "Deccan Learning Foundation", "Telangana", 300, "nodal@deccan.synthetic.in"),
    InstSpec("E", "Shakti Women's Engineering College (Synthetic)", "1-SYN-4418-0005", "Shakti Educational Trust", "Telangana", 180, "nodal@shaktiwomen.synthetic.in"),
]
STAFF = [
    ("officer@aicte.synthetic.in", "Ananya Rao", "OFFICER"),
    ("admin@aicte.synthetic.in", "Vikram Shah", "ADMIN"),
    ("admin2@aicte.synthetic.in", "Meera Iyer", "ADMIN"),
    ("auditor@aicte.synthetic.in", "Farhan Ali", "AUDITOR"),
]
AY, PREV_AY = "2026-27", "2025-26"


def _inst(spec: InstSpec) -> g.Inst:
    return g.Inst(spec.name, spec.pid)


def upload(principal: Principal, application_id: str, doc_type: str, filename: str, data: bytes) -> str:
    info = validate_upload(data, doc_type, get_settings().max_pdf_pages)
    sha = LocalStorage().put(data)
    doc_id = new_id("doc")
    with transaction() as c:
        prev = c.execute("SELECT id FROM documents WHERE application_id = ? AND doc_type = ? AND superseded_by IS NULL",
                         (application_id, doc_type)).fetchall()
        c.execute("INSERT INTO documents (id, application_id, doc_type, original_name, sha256, size_bytes, mime, pages,"
                  " uploaded_by, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (doc_id, application_id, doc_type, filename, sha, len(data), info.mime, info.pages, principal.user_id, now_iso()))
        for p in prev:
            c.execute("UPDATE documents SET superseded_by = ? WHERE id = ?", (doc_id, p["id"]))
        job = create_job(c, "PROCESS_DOCUMENT", application_id, doc_id)
        audit.record(c, principal, "document.uploaded", "document", doc_id, {"doc_type": doc_type, "sha256": sha}, application_id)
    run_job(job)
    return doc_id


def create_application(p: Principal, category: str = "EOA_EXISTING") -> str:
    app_id = new_id("app")
    ts = now_iso()
    with transaction() as c:
        c.execute("INSERT INTO applications (id, institution_id, category, academic_year, status, created_by, created_at,"
                  " updated_at) VALUES (?,?,?,?, 'DRAFT', ?, ?, ?)", (app_id, p.institution_id, category, AY, p.user_id, ts, ts))
        audit.record(c, p, "application.created", "application", app_id, {"category": category, "academic_year": AY}, app_id)
    return app_id


def submit(p: Principal, app_id: str) -> None:
    with transaction() as c:
        ts = now_iso()
        c.execute("UPDATE applications SET submitted_at = ?, updated_at = ? WHERE id = ?", (ts, ts, app_id))
        audit.record(c, p, "application.submitted", "application", app_id, {}, app_id)


def build_bundles(keys: dict[str, str]) -> dict[str, dict[str, tuple[str, bytes]]]:
    A, B, C, D, E = (_inst(s) for s in INSTITUTIONS)
    qr = lambda issuer, payload: g.signed_qr_text(keys[issuer], {"iss": issuer, "ref": payload["ref_no"], **payload})  # noqa: E731
    photo_a, photo_c = g.lab_photo(11), g.lab_photo(17)
    b = {}
    b["A"] = {  # clean bundle; reprinted EoA letter (hard negative: print date far after issue date)
        "eoa_letter": ("EoA_2025-26_reprint.pdf", g.eoa_letter(A, PREV_AY, 360, date(2025, 4, 15), date(2026, 9, 12))),
        "affidavit": ("Affidavit_2026-27.pdf", g.affidavit(A, AY, 360, 85, date(2026, 1, 5))),
        "fire_noc": ("Fire_NOC.pdf", g.certificate("fire_noc", A, "FNOC/SYN/2025/7781", date(2025, 4, 1), date(2027, 3, 31),
                     qr_text=qr("SYN-FIRE-TS", {"ref_no": "FNOC/SYN/2025/7781", "permanent_id": A.pid, "valid_to": "2027-03-31"}))),
        "building_stability": ("Structural_Stability.pdf", g.certificate("building_stability", A, "BSC/SYN/2024/2210",
                               date(2024, 2, 10), date(2029, 2, 9), area=18250)),
        "faculty_summary": ("Faculty_Summary.pdf", g.faculty_summary(A, AY, 85, 1440, 360)),
        "infra_photo": ("Computer_Lab.png", photo_a),
    }
    b["B"] = {  # planted defects
        "eoa_letter": ("EoA_2025-26.pdf", g.eoa_letter(B, PREV_AY, 240, date(2025, 4, 22), file_no="SYN/EOA/2025-26/00512")),
        "affidavit": ("Affidavit_2026-27.pdf", g.affidavit(B, AY, 300, 68, date(2026, 1, 8))),             # intake 300 ≠ record 240
        "fire_noc": ("Fire_NOC.pdf", g.certificate("fire_noc", B, "FNOC/SYN/2024/3310", date(2024, 4, 1), date(2026, 3, 31),
                     qr_text=qr("SYN-FIRE-TS", {"ref_no": "FNOC/SYN/2024/3310", "permanent_id": B.pid, "valid_to": "2026-03-31"}))),
        "faculty_summary": ("Faculty_Summary.pdf", g.faculty_summary(B, AY, 48, 960, 240, faculty_overlay=68)),  # overlay edit
        "infra_photo": ("Lab_Photo.jpg", g.reencode_jpeg(photo_c)),                                       # reused from C
    }
    b["C"] = {  # verification ladder: mismatch, source unavailable, record mismatch, scanned affidavit (OCR)
        "eoa_letter": ("EoA_2025-26.pdf", g.eoa_letter(C, PREV_AY, 240, date(2025, 5, 2), file_no="SYN/EOA/2025-26/00733")),
        "affidavit": ("Affidavit_scan.pdf", g.rasterize(g.affidavit(C, AY, 180, 45, date(2026, 1, 12)))),
        "fire_noc": ("Fire_NOC.pdf", g.certificate("fire_noc", C, "FNOC/SYN/2025/9902", date(2025, 6, 1), date(2027, 3, 31),
                     printed_valid_to=date(2028, 3, 31),
                     qr_text=qr("SYN-FIRE-TS", {"ref_no": "FNOC/SYN/2025/9902", "permanent_id": C.pid, "valid_to": "2027-03-31"}))),
        "building_stability": ("Structural_Stability.pdf", g.incremental_edit(g.certificate(
            "building_stability", C, "BSC/SYN-KA/2023/0099", date(2023, 8, 1), date(2028, 7, 31), area=9100))),
        "faculty_summary": ("Faculty_Summary.pdf", g.faculty_summary(C, AY, 45, 720, 180)),
        "infra_photo": ("Workshop_Lab.png", photo_c),
    }
    b["E"] = {  # same trust as A — shared photograph is an allowed reuse (hard negative)
        "eoa_letter": ("EoA_2025-26.pdf", g.eoa_letter(E, PREV_AY, 180, date(2025, 4, 18), file_no="SYN/EOA/2025-26/00455")),
        "affidavit": ("Affidavit_2026-27.pdf", g.affidavit(E, AY, 180, 40, date(2026, 1, 6))),
        "fire_noc": ("Fire_NOC.pdf", g.certificate("fire_noc", E, "FNOC/SYN/2025/7790", date(2025, 4, 3), date(2027, 3, 31),
                     qr_text=qr("SYN-FIRE-TS", {"ref_no": "FNOC/SYN/2025/7790", "permanent_id": E.pid, "valid_to": "2027-03-31"}))),
        "building_stability": ("Structural_Stability.pdf", g.certificate("building_stability", E, "BSC/SYN/2024/2214",
                               date(2024, 2, 12), date(2029, 2, 11), area=8600,
                               qr_text=qr("SYN-STRUCT", {"ref_no": "BSC/SYN/2024/2214", "permanent_id": E.pid, "valid_to": "2029-02-11"}))),
        "faculty_summary": ("Faculty_Summary.pdf", g.faculty_summary(E, AY, 40, 720, 180)),
        "infra_photo": ("Computer_Lab.png", photo_a),
    }
    b["D"] = {  # live-demo files: a first upload with problems, plus corrected replacements
        "eoa_letter": ("D_EoA_2025-26.pdf", g.eoa_letter(D, PREV_AY, 300, date(2025, 4, 20), file_no="SYN/EOA/2025-26/00618")),
        "affidavit": ("D_Affidavit_2026-27.pdf", g.affidavit(D, AY, 300, 70, date(2026, 1, 9))),
        "fire_noc": ("D_Fire_NOC_EXPIRED.pdf", g.certificate("fire_noc", D, "FNOC/SYN/2024/4471", date(2024, 4, 2), date(2026, 3, 31),
                     qr_text=qr("SYN-FIRE-TS", {"ref_no": "FNOC/SYN/2024/4471", "permanent_id": D.pid, "valid_to": "2026-03-31"}))),
        "fire_noc_renewed": ("D_Fire_NOC_RENEWED.pdf", g.certificate("fire_noc", D, "FNOC/SYN/2026/5012", date(2026, 4, 2), date(2028, 3, 31),
                             qr_text=qr("SYN-FIRE-TS", {"ref_no": "FNOC/SYN/2026/5012", "permanent_id": D.pid, "valid_to": "2028-03-31"}))),
        "building_stability": ("D_Structural_Stability.pdf", g.certificate("building_stability", D, "BSC/SYN/2025/3307",
                               date(2025, 1, 15), date(2030, 1, 14), area=15400,
                               qr_text=qr("SYN-STRUCT", {"ref_no": "BSC/SYN/2025/3307", "permanent_id": D.pid, "valid_to": "2030-01-14"}))),
        "faculty_summary": ("D_Faculty_Summary_WRONG_INTAKE.pdf", g.faculty_summary(D, AY, 70, 1200, 360)),
        "faculty_summary_corrected": ("D_Faculty_Summary_CORRECTED.pdf", g.faculty_summary(D, AY, 70, 1200, 300)),
        "infra_photo": ("D_Lab_Photo.png", g.lab_photo(29)),
    }
    return b


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reset", action="store_true", help="delete DATA_DIR before seeding")
    args = ap.parse_args()
    s = get_settings()
    if args.reset and s.data_dir.exists():
        shutil.rmtree(s.data_dir)
    bootstrap()
    with reader() as c:
        if c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            print("Database already seeded. Use --reset to start over.")
            return
    password = os.environ.get("SEED_DEMO_PASSWORD") or secrets.token_urlsafe(12)
    pw_hash = hash_password(password)
    issuer_keys: dict[str, str] = {}
    principals: dict[str, Principal] = {}
    ts = now_iso()
    with transaction() as c:
        for spec in INSTITUTIONS:
            iid = new_id("ins")
            c.execute("INSERT INTO institutions VALUES (?,?,?,?,?,?)", (iid, spec.pid, spec.name, spec.state, spec.trust, ts))
            c.execute("INSERT INTO aicte_records VALUES (?,?,?,?,1)", (iid, spec.intake, PREV_AY, json.dumps(
                {"UG Engg.": ["Computer Science and Engineering", "Electronics and Communication Engg.", "Mechanical Engineering"]})))
            uid = new_id("usr")
            c.execute("INSERT INTO users (id, email, name, role, institution_id, password_hash, created_at) VALUES (?,?,?,?,?,?,?)",
                      (uid, spec.email, f"Nodal Officer — {spec.name.split(' (')[0]}", "INSTITUTION", iid, pw_hash, ts))
            principals[spec.key] = Principal(uid, "INSTITUTION", iid, spec.name, spec.email)
        for email, name, role in STAFF:
            uid = new_id("usr")
            c.execute("INSERT INTO users (id, email, name, role, password_hash, created_at) VALUES (?,?,?,?,?,?)",
                      (uid, email, name, role, pw_hash, ts))
            principals[email] = Principal(uid, role, None, name, email)
        for issuer_id, name, available in [("SYN-FIRE-TS", "State Fire Services (synthetic)", 1),
                                           ("SYN-STRUCT", "Structural Engineers Registry (synthetic)", 1),
                                           ("SYN-STRUCT-KA", "Regional Engineers Registry (synthetic, offline)", 0)]:
            pem, pub = g.issuer_keypair()
            issuer_keys[issuer_id] = pem
            c.execute("INSERT INTO issuers VALUES (?,?,?,?,1)", (issuer_id, name, pub, available))
        for ref, issuer, doc_type, fields in [
            ("BSC/SYN/2024/2210", "SYN-STRUCT", "building_stability",
             {"ref_no": "BSC/SYN/2024/2210", "permanent_id": "1-SYN-4417-0001", "valid_to": "2029-02-09"}),
            ("BSC/SYN-KA/2023/0099", "SYN-STRUCT-KA", "building_stability",
             {"ref_no": "BSC/SYN-KA/2023/0099", "permanent_id": "1-SYN-6631-0003", "valid_to": "2028-07-31"}),
        ]:
            c.execute("INSERT INTO issuer_registry VALUES (?,?,?,?)", (ref, issuer, doc_type, json.dumps(fields)))
        audit.record(c, None, "seed.completed", "system", "seed", {"synthetic": True})
    g.save_keys(s.data_dir / "synthetic_issuer_keys.json", issuer_keys)

    bundles = build_bundles(issuer_keys)
    demo_dir = s.data_dir / "demo_files"
    demo_dir.mkdir(parents=True, exist_ok=True)
    for _, (fname, data) in bundles["D"].items():
        (demo_dir / fname).write_bytes(data)

    for key in ("A", "C", "B", "E"):
        p = principals[key]
        app_id = create_application(p)
        for doc_type, (fname, data) in bundles[key].items():
            upload(p, app_id, doc_type, fname, data)
            print(f"  {key}: processed {doc_type}")
        submit(p, app_id)

    creds = ["PRAMAAN demo accounts (synthetic data only)", f"Password for every account: {password}", ""]
    creds += [f"{s_.email:34} INSTITUTION  {s_.name}" for s_ in INSTITUTIONS]
    creds += [f"{e:34} {r:12} {n}" for e, n, r in STAFF]
    creds += ["", f"Live-demo upload files for {INSTITUTIONS[3].name}: {demo_dir}"]
    out = s.data_dir / "demo_credentials.txt"
    out.write_text("\n".join(creds) + "\n")
    os.chmod(out, 0o600)
    print("\n".join(creds))


if __name__ == "__main__":
    main()
