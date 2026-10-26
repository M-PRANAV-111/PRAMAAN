"""Synthetic fault-injection benchmark.

Generates application bundles with planted faults and valid hard negatives, runs each one through
the real pipeline, and reports detection per fault type and false alarms. Results describe behaviour
on *synthetic* documents only; they are not evidence of real-world accuracy.

Usage:  python -m eval.benchmark [--repeats 2] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import zlib
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

FAULTS: dict[str, dict] = {
    # fault -> required finding keys, plus findings that legitimately follow from the same fault
    "missing_affidavit": {"required": {"DOC.AFFIDAVIT.PRESENT"}, "allowed": set()},
    "missing_building": {"required": {"DOC.BUILDING.PRESENT"}, "allowed": set()},
    "expired_fire_noc": {"required": {"FIRE.VALID"}, "allowed": set()},
    "expired_building": {"required": {"BUILDING.VALID"}, "allowed": set()},
    "intake_changed_in_affidavit": {"required": {"INTAKE.NO_CHANGE"}, "allowed": {"INTAKE.CONSISTENT"}},
    "intake_differs_in_summary": {"required": {"INTAKE.CONSISTENT"}, "allowed": set()},
    "faculty_count_conflict": {"required": {"FACULTY.CONSISTENT"}, "allowed": {"FACULTY.RATIO"}},
    "ratio_exceeded": {"required": {"FACULTY.RATIO"}, "allowed": {"FACULTY.CONSISTENT"}},
    "affidavit_wrong_year": {"required": {"AY.AFFIDAVIT"}, "allowed": set()},
    "overlay_edit_faculty": {"required": {"INTEGRITY:VISIBLE_TEXT_MISMATCH"},
                             "allowed": {"FACULTY.CONSISTENT", "FACULTY.RATIO"}},
    "qr_value_mismatch": {"required": {"VERIFY.FIRE_NOC"}, "allowed": set()},
    "letter_vs_record": {"required": {"INTAKE.LETTER_VS_RECORD"}, "allowed": set()},
    "permanent_id_mismatch": {"required": {"ID.CONSISTENT"}, "allowed": set()},
}
HARD_NEGATIVES = ["clean", "reprinted_letter", "scanned_affidavit", "legitimate_resave"]


def _bundle(g, keys: dict[str, str], inst, intake: int, fault: str) -> dict[str, tuple[str, bytes]]:
    AY, PREV = "2026-27", "2025-26"
    faculty = max(1, intake * 4 // 20)
    students = intake * 4
    qr = lambda iss, p: g.signed_qr_text(keys[iss], {"iss": iss, "ref": p["ref_no"], **p})  # noqa: E731
    fire_valid = date(2026, 3, 31) if fault == "expired_fire_noc" else date(2027, 9, 30)
    fire_ref = f"FNOC/SYN/B/{zlib.crc32(inst.pid.encode()) % 10_000:04d}"
    fire_pid = "1-SYN-0000-9999" if fault == "permanent_id_mismatch" else inst.pid
    fire = g.certificate(
        "fire_noc", g.Inst(inst.name, fire_pid), fire_ref, date(2025, 4, 1), fire_valid,
        printed_valid_to=date(2028, 9, 30) if fault == "qr_value_mismatch" else None,
        qr_text=qr("SYN-FIRE-TS", {"ref_no": fire_ref, "permanent_id": fire_pid, "valid_to": fire_valid.isoformat()}))
    b_valid = date(2026, 5, 31) if fault == "expired_building" else date(2030, 1, 31)
    b_ref = f"BSC/SYN/B/{zlib.crc32(inst.pid.encode()) % 10_000:04d}"
    building = g.certificate("building_stability", inst, b_ref, date(2024, 2, 1), b_valid, area=12000,
                             qr_text=qr("SYN-STRUCT", {"ref_no": b_ref, "permanent_id": inst.pid, "valid_to": b_valid.isoformat()}))
    aff_intake = intake + 60 if fault == "intake_changed_in_affidavit" else intake
    aff_faculty = faculty + 9 if fault == "faculty_count_conflict" else faculty
    aff = g.affidavit(inst, "2025-26" if fault == "affidavit_wrong_year" else AY, aff_intake, aff_faculty, date(2026, 1, 7))
    if fault == "scanned_affidavit":
        aff = g.rasterize(aff)
    summ_intake = intake + 30 if fault == "intake_differs_in_summary" else intake
    summ_faculty = faculty - 12 if fault == "ratio_exceeded" else faculty
    if fault == "ratio_exceeded":
        aff = g.affidavit(inst, AY, aff_intake, summ_faculty, date(2026, 1, 7))
    overlay = faculty if fault == "overlay_edit_faculty" else None
    text_faculty = faculty - 14 if fault == "overlay_edit_faculty" else summ_faculty
    summary = g.faculty_summary(inst, AY, text_faculty, students, summ_intake, faculty_overlay=overlay)
    letter_intake = intake + 60 if fault == "letter_vs_record" else intake
    letter = g.eoa_letter(inst, PREV, letter_intake, date(2025, 4, 12),
                          printed=date(2026, 9, 20) if fault == "reprinted_letter" else None)
    if fault == "legitimate_resave":
        building = g.incremental_edit(building)
    docs = {"eoa_letter": ("letter.pdf", letter), "affidavit": ("affidavit.pdf", aff), "fire_noc": ("fire.pdf", fire),
            "building_stability": ("building.pdf", building), "faculty_summary": ("summary.pdf", summary)}
    if fault == "missing_affidavit":
        docs.pop("affidavit")
    if fault == "missing_building":
        docs.pop("building_stability")
    return docs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repeats", type=int, default=2, help="bundles per fault type / hard-negative type")
    ap.add_argument("--out", type=Path, default=None, help="report path (default DATA_DIR/benchmark/latest.json)")
    ap.add_argument("--ai", choices=["off", "on", "both"], default="off",
                    help="off (default): the deterministic benchmark, unchanged. on: the AI evaluation only. both: both, in turn.")
    ap.add_argument("--ai-sim", choices=["oracle", "adversarial"], default=None,
                    help="with --ai on|both and no provider key: use a SIMULATED model (measures the grounding guard, not a model)")
    args = ap.parse_args()
    if args.ai == "on":
        return _run_ai_eval(args)

    target_data_dir = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[1] / "var"))
    out = args.out or target_data_dir / "benchmark" / "latest.json"
    work = tempfile.TemporaryDirectory()
    os.environ["DATA_DIR"] = work.name           # benchmark never touches the demo database
    os.environ["WORKER_THREADS"] = "0"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.config import reset_settings_cache
    reset_settings_cache()
    from app.db import new_id, now_iso, reader, transaction
    from app.main import bootstrap
    from app.security import Principal
    from synthetic import generator as g
    from synthetic.seed import create_application, upload

    bootstrap()
    keys = {}
    with transaction() as c:
        for iss in ("SYN-FIRE-TS", "SYN-STRUCT"):
            pem, pub = g.issuer_keypair()
            keys[iss] = pem
            c.execute("INSERT INTO issuers VALUES (?,?,?,1,1)", (iss, iss, pub))

    cases = [(f, r) for f in list(FAULTS) + HARD_NEGATIVES for r in range(args.repeats)]
    results = []
    for n, (fault, rep) in enumerate(cases):
        intake = [120, 180, 240, 300, 360][n % 5]
        pid = f"1-SYN-B{n:03d}-{rep:04d}"
        inst = g.Inst(f"Benchmark Institute {n} (Synthetic)", pid)
        with transaction() as c:
            iid, uid = new_id("ins"), new_id("usr")
            c.execute("INSERT INTO institutions (id,aicte_permanent_id,name,state,trust_name,created_at) VALUES (?,?,?,?,?,?)", (iid, pid, inst.name, "Synthetic", f"Trust {n}", now_iso()))
            c.execute("INSERT INTO aicte_records VALUES (?,?,?,?,1)", (iid, intake, "2025-26", "{}"))
            c.execute("INSERT INTO users (id, email, name, role, institution_id, password_hash, created_at) VALUES"
                      " (?,?,?,?,?,?,?)", (uid, f"b{n}@bench.synthetic", "bench", "INSTITUTION", iid, "x", now_iso()))
        p = Principal(uid, "INSTITUTION", iid, "bench", f"b{n}@bench.synthetic")
        app_id = create_application(p)
        t0 = time.perf_counter()
        for doc_type, (fname, data) in _bundle(g, keys, inst, intake, fault).items():
            upload(p, app_id, doc_type, fname, data)
        elapsed = time.perf_counter() - t0
        with reader() as c:
            found = set()
            for f in c.execute("SELECT * FROM findings WHERE application_id = ? AND state = 'OPEN'", (app_id,)):
                key = f["rule_id"] or f"{f['source_kind']}:{json.loads(f['proof_json']).get('indicator', '')}".rstrip(":")
                found.add(key)
        spec = FAULTS.get(fault, {"required": set(), "allowed": set()})
        detected = spec["required"] <= found
        unexpected = sorted(found - spec["required"] - spec["allowed"])
        results.append({"case": fault, "repeat": rep, "kind": "fault" if fault in FAULTS else "hard_negative",
                        "detected": detected if fault in FAULTS else None, "found": sorted(found),
                        "unexpected": unexpected, "seconds": round(elapsed, 2)})
        print(f"[{n + 1}/{len(cases)}] {fault:28} detected={detected!s:5} unexpected={unexpected} {elapsed:.1f}s", flush=True)

    per_fault = {}
    for f in FAULTS:
        rs = [r for r in results if r["case"] == f]
        per_fault[f] = {"bundles": len(rs), "detected": sum(r["detected"] for r in rs),
                        "recall": round(sum(r["detected"] for r in rs) / len(rs), 3)}
    neg = [r for r in results if r["kind"] == "hard_negative"]
    all_unexpected = [u for r in results for u in r["unexpected"]]
    total_findings = sum(len(r["found"]) for r in results)
    times = sorted(r["seconds"] for r in results)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": "Measured on synthetic documents produced by this project's generator. Not evidence of accuracy on real AICTE submissions.",
        "environment": {"python": platform.python_version(), "machine": platform.machine(), "processing": "single worker, CPU only"},
        "bundles": len(results), "fault_types": len(FAULTS), "repeats": args.repeats,
        "per_fault": per_fault,
        "overall_recall": round(sum(r["detected"] for r in results if r["kind"] == "fault") / sum(1 for r in results if r["kind"] == "fault"), 3),
        "hard_negatives": {"bundles": len(neg), "with_any_finding": sum(1 for r in neg if r["found"]),
                           "findings": sorted({u for r in neg for u in r["found"]})},
        "unexpected_findings": {"count": len(all_unexpected), "of_total_findings": total_findings,
                                "by_key": {k: all_unexpected.count(k) for k in sorted(set(all_unexpected))}},
        "seconds_per_bundle": {"median": round(statistics.median(times), 2), "p95": times[max(0, int(len(times) * 0.95) - 1)],
                               "max": times[-1]},
        "cases": results,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=2))
    work.cleanup()
    if args.ai == "both":
        _run_ai_eval(args)


def _run_ai_eval(args) -> None:
    """The AI evaluation runs in its own process so it gets its own database and environment."""
    import subprocess
    cmd = [sys.executable, "-m", "eval.ai_eval", "--repeats", str(args.repeats)]
    if args.ai_sim:
        cmd += ["--sim", args.ai_sim]
    subprocess.run(cmd, cwd=Path(__file__).resolve().parents[1], check=True)


if __name__ == "__main__":
    main()
