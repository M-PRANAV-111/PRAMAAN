"""Deterministic snapshot of the seeded scenarios, used to prove AI_PROVIDER=none changes nothing.

Run as ``python -m tests.parity_support --out FILE``. The process seeds a fresh synthetic database, adds the
live-demo institution's application (the same files ``tests.test_api.WorkflowTests`` uploads), and writes
findings, statuses, claims, verification outcomes and repair plans with all random identifiers replaced by
stable fingerprints. ``tests/fixtures/ai/parity_snapshot.json`` was generated from the pipeline *before* the AI
layer existed, so a match proves the layer is inert when switched off.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SNAPSHOT = Path(__file__).resolve().parent / "fixtures" / "ai" / "parity_snapshot.json"
PASSWORD = "parity-password-123"


def build(data_dir: str, extra_env: dict[str, str] | None = None) -> dict:
    env = {**os.environ, "DATA_DIR": data_dir, "SEED_DEMO_PASSWORD": PASSWORD, "APP_ENV": "test", "WORKER_THREADS": "0",
           "EMAIL_PROVIDER": "console", "AI_PROVIDER": "none", **(extra_env or {})}
    out = Path(data_dir) / "snapshot.json"
    subprocess.run([sys.executable, "-m", "tests.parity_support", "--worker", str(out)], cwd=BACKEND, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return json.loads(out.read_text(encoding="utf-8"))


def _collect() -> dict:
    from app.db import loads, reader
    from app.pipeline.repair import build_plan
    snapshot: dict = {"applications": {}}
    with reader() as c:
        for app in c.execute("SELECT a.*, i.name AS inst FROM applications a JOIN institutions i ON i.id=a.institution_id"
                             " ORDER BY i.name"):
            rows = [dict(r) for r in c.execute("SELECT * FROM findings WHERE application_id=?", (app["id"],))]
            fp = {r["id"]: r["fingerprint"] for r in rows}
            findings = []
            for r in rows:
                evidence = [{k: e.get(k) for k in ("doc_type", "field", "value", "normalized", "page", "extractor", "confidence")}
                            for e in loads(r["evidence_json"], [])]
                findings.append({k: r[k] for k in ("fingerprint", "source_kind", "rule_id", "title", "severity", "state",
                                                   "explanation", "remedy", "fix_doc_type", "action_owner")}
                                | {"evidence": evidence})
            findings.sort(key=lambda f: f["fingerprint"])
            plan = build_plan([r for r in rows])

            def norm_action(a: dict) -> dict:
                a = dict(a)
                a["id"] = a["id"].replace(next((i for i in fp if i in a["id"]), "\0"), fp.get(next((i for i in fp if i in a["id"]), ""), ""))
                a["resolves"] = sorted(fp[i] for i in a["resolves"])
                return a
            plan_out = {"institution_actions": sorted((norm_action(a) for a in plan["institution_actions"]), key=lambda a: a["id"]),
                        "officer_actions": sorted((norm_action(a) for a in plan["officer_actions"]), key=lambda a: a["id"]),
                        "open_findings": plan["open_findings"]}
            docs = {}
            for d in c.execute("SELECT * FROM documents WHERE application_id=? AND superseded_by IS NULL", (app["id"],)):
                claims = {cl["field"]: {"raw": cl["value_raw"], "norm": cl["value_norm"], "page": cl["page"],
                                        "extractor": cl["extractor"], "confidence": cl["confidence"]}
                          for cl in c.execute("SELECT * FROM claims WHERE document_id=?", (d["id"],))}
                docs[d["doc_type"]] = {"verification": d["verification_status"], "detected_type": d["detected_type"],
                                       "claims": claims}
            snapshot["applications"][app["inst"]] = {"status": app["status"], "findings": findings, "repair_plan": plan_out,
                                                     "documents": docs}
    return _stable(snapshot)


def _stable(snapshot: dict) -> dict:
    """Random identifiers differ per run; replace them, then restore a deterministic order."""
    snap = json.loads(re.sub(r"\b(doc|fnd|run|job|app|ins|usr)_[0-9a-f]{20}\b", r"\1_*", json.dumps(snapshot)))
    for entry in snap["applications"].values():
        entry["findings"].sort(key=lambda f: (f["fingerprint"], f["title"]))
        plan = entry["repair_plan"]
        for key in ("institution_actions", "officer_actions"):
            for a in plan[key]:
                a["resolves"].sort()
            plan[key].sort(key=lambda a: (a["id"], a["title"], a["resolves"]))
    return snap


def _worker(out: Path) -> None:
    from synthetic.seed import create_application, upload
    from app.db import reader
    from app.security import Principal
    seed = subprocess.run([sys.executable, "-m", "synthetic.seed"], cwd=BACKEND, env=os.environ, capture_output=True, text=True)
    if seed.returncode:
        raise RuntimeError(seed.stderr)
    with reader() as c:
        u = c.execute("SELECT * FROM users WHERE email='nodal@deccan.synthetic.in'").fetchone()
    p = Principal(u["id"], "INSTITUTION", u["institution_id"], u["name"], u["email"])
    app_id = create_application(p)
    demo = Path(os.environ["DATA_DIR"]) / "demo_files"
    for doc_type, name in {"eoa_letter": "D_EoA_2025-26.pdf", "affidavit": "D_Affidavit_2026-27.pdf",
                           "fire_noc": "D_Fire_NOC_EXPIRED.pdf", "building_stability": "D_Structural_Stability.pdf",
                           "faculty_summary": "D_Faculty_Summary_WRONG_INTAKE.pdf", "infra_photo": "D_Lab_Photo.png"}.items():
        upload(p, app_id, doc_type, name, (demo / name).read_bytes())
    upload(p, app_id, "fire_noc", "D_Fire_NOC_RENEWED.pdf", (demo / "D_Fire_NOC_RENEWED.pdf").read_bytes())
    out.write_text(json.dumps(_collect(), indent=1, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.worker:
        _worker(args.worker)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            snap = build(tmp)
        (args.out or SNAPSHOT).parent.mkdir(parents=True, exist_ok=True)
        (args.out or SNAPSHOT).write_text(json.dumps(snap, indent=1, sort_keys=True), encoding="utf-8")
        print("wrote", args.out or SNAPSHOT)
