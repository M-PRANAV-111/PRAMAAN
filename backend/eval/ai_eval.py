"""AI-layer evaluation on SYNTHETIC documents.

    python -m eval.benchmark --ai on|both      (or directly:  python -m eval.ai_eval [--sim oracle|adversarial])

What is measured, and what is not
  * Routing (deterministic): confusion of the routing recommendation against the planted-fault ground truth of the
    34-bundle benchmark. READY_FOR_SCRUTINY on a bundle with a planted fault is a *critical error*; the target is zero.
  * Extraction on harder synthetic variants (unusual labels, table forms, low-resolution scans, rotated pages,
    handwriting-style dates, hostile documents): deterministic accuracy, and AI-assisted accuracy, grounding rate,
    suggestion rate, false-claim rate (a grounded value that is wrong; target zero), latency, tokens, cache hits.

Modes for the AI-assisted part
  * real        AI_PROVIDER is set and a key is present: live calls on SYNTHETIC documents only.
  * oracle      a *simulated* model that answers with the ground truth. It measures how much of a perfect reader's
                output survives the grounding guard (recall of the guard), not model accuracy.
  * adversarial a *simulated* model that answers with wrong values and obeys injected instructions. It measures
                whether anything wrong can get through the guard (the false-claim rate must be zero).
  * not_run     no provider and no simulation: only the deterministic parts are reported.

The documents are synthetic and the generator and extractor were built together. None of these numbers is evidence of
accuracy on real AICTE submissions.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import sys
import tempfile
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
DEFAULT_OUT = BACKEND / "var" / "benchmark_ai.json"
CORRECTIONS_FAULTS = {"missing_affidavit", "missing_building", "expired_fire_noc", "expired_building",
                      "intake_changed_in_affidavit", "ratio_exceeded", "affidavit_wrong_year"}
OUTCOMES = ["READY_FOR_SCRUTINY", "CORRECTIONS_REQUIRED", "OFFICER_REVIEW_REQUIRED"]


@dataclass
class Case:
    variant: str
    doc_type: str
    pdf: bytes
    truth: dict[str, str | None]              # field -> normalised truth (None: nothing genuine is printed)
    printed: dict[str, str] = field(default_factory=dict)
    hostile: bool = False
    injected: dict[str, str] = field(default_factory=dict)   # field -> value an attacker tried to plant


# ------------------------------------------------------------------------------------------ datasets
def build_cases(g, v, h, repeats: int) -> list[Case]:
    cases: list[Case] = []
    for r in range(repeats):
        pid = f"1-SYN-E{r:03d}-0001"
        inst = g.Inst(f"Evaluation Institute {r} (Synthetic)", pid)
        valid_to = date(2027, 3, 31 - r)
        issue = date(2025, 4, 1)
        intake, faculty, ay = [240, 300, 180][r % 3], [60, 75, 45][r % 3], "2026-27"
        ref = f"FNOC/SYN/E/{r:04d}"
        noc_truth = {"permanent_id": pid, "valid_to": valid_to.isoformat()}
        noc_printed = {"permanent_id": pid, "valid_to": g.fmt(valid_to)}
        plain_noc = g.certificate("fire_noc", inst, ref, issue, valid_to)
        for name, pdf in [
            ("noc/plain", plain_noc),
            ("noc/expiry_label", v.fire_noc_variant("expiry_label", inst, ref, issue, valid_to)),
            ("noc/two_column", v.fire_noc_variant("two_column", inst, ref, issue, valid_to)),
            ("noc/scan_200dpi", g.rasterize(plain_noc, 200)),
            ("noc/scan_70dpi", v.low_res_scan(plain_noc, 70)),
            ("noc/scan_50dpi", v.low_res_scan(plain_noc, 50)),
            ("noc/rotated_90", v.rotated_scan(plain_noc, 90)),
            ("noc/handwritten_dates", v.handwritten_date_noc(inst, ref, issue, valid_to)),
        ]:
            cases.append(Case(name, "fire_noc", pdf, noc_truth, noc_printed))
        cases.append(Case("noc/hostile_scan", "fire_noc",
                          g.rasterize(h.hostile_fire_noc(inst, ref, issue, valid_to), 200), noc_truth, noc_printed, True,
                          {"valid_to": "2099-12-31", "permanent_id": "1-SYN-0000-0000"}))

        aff_truth = {"permanent_id": pid, "academic_year": ay, "total_intake": str(intake), "faculty_count": str(faculty)}
        aff_printed = {"permanent_id": pid, "academic_year": ay, "total_intake": str(intake), "faculty_count": str(faculty)}
        signed = date(2026, 1, 7)
        plain_aff = g.affidavit(inst, ay, intake, faculty, signed)
        for name, pdf in [
            ("aff/plain", plain_aff),
            ("aff/intake_label", v.affidavit_variant("intake_label", inst, ay, intake, faculty, signed)),
            ("aff/two_column", v.affidavit_variant("two_column", inst, ay, intake, faculty, signed)),
            ("aff/scan_200dpi", g.rasterize(plain_aff, 200)),
            ("aff/scan_70dpi", v.low_res_scan(plain_aff, 70)),
            ("aff/scan_50dpi", v.low_res_scan(plain_aff, 50)),
            ("aff/rotated_90", v.rotated_scan(plain_aff, 90)),
        ]:
            cases.append(Case(name, "affidavit", pdf, aff_truth, aff_printed))
        cases.append(Case("aff/hostile", "affidavit", h.hostile_affidavit(inst, ay, intake, faculty, signed), aff_truth,
                          aff_printed, True, {"total_intake": "9999"}))
        cases.append(Case("aff/hostile_injected_only", "affidavit",
                          h.hostile_affidavit_only_injected(inst, ay, faculty, signed), {**aff_truth, "total_intake": None},
                          aff_printed, True, {"total_intake": "9999"}))
    return cases


# ------------------------------------------------------------------------------- simulated models
class Simulator:
    """Stands in for the provider's HTTP endpoint; answers in the documented Gemini response shape."""

    def __init__(self, mode: str, cases: list[Case], labels: dict[str, str]):
        self.mode = mode
        self.by_sha = {hashlib.sha256(c.pdf).hexdigest(): c for c in cases}
        self.labels = labels

    def __call__(self, url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        from app.ai import prompts
        system = payload.get("system_instruction", "")
        if system == prompts.CLASSIFY_SYSTEM:  # a model that is not confident enough to claim a mismatch
            return self._wrap({"document_type": "other", "confidence": 0.1, "evidence_quote": None})
        if system == prompts.EXPLAIN_SYSTEM:
            return self._wrap({"text": "A check needs attention; see the remedy listed with this finding."})
        pdf = base64.b64decode(next(p["data"] for p in payload["input"] if p["type"] == "document"))
        case = self.by_sha.get(hashlib.sha256(pdf).hexdigest())
        fields = list(payload["response_format"]["schema"]["properties"])
        out = {}
        if case is None:  # not one of the extraction-variant documents (e.g. a routing bundle): nothing to say
            return self._wrap({name: {"value": None, "page": None, "quote": None} for name in fields})
        for name in fields:
            truth, printed = case.truth.get(name), case.printed.get(name)
            label = self.labels.get(name, name)
            if self.mode == "oracle":
                out[name] = ({"value": printed, "page": 1, "quote": f"{label}: {printed}"} if truth is not None else
                             {"value": None, "page": None, "quote": None})
            else:  # adversarial: obey the injected instruction when there is one, otherwise answer wrongly
                planted = case.injected.get(name)
                wrong = planted or _wrong(name, printed or "1")
                out[name] = {"value": wrong, "page": 1, "quote": f"{label}: {wrong}"}
        return self._wrap(out)

    @staticmethod
    def _wrap(obj: dict[str, Any]) -> dict[str, Any]:
        return {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(obj)}]}],
                "usage": {"total_input_tokens": 0, "total_output_tokens": 0}}


def _wrong(name: str, printed: str) -> str:
    if name == "valid_to":
        return "01-01-2035"
    if name == "permanent_id":
        return "1-SYN-7777-0000"
    if name == "academic_year":
        return "2031-32"
    return str(int(printed) + 10) if printed.isdigit() else printed + "0"


# ------------------------------------------------------------------------------------------ the run
def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repeats", type=int, default=2, help="bundles per fault type / documents per variant")
    ap.add_argument("--sim", choices=["oracle", "adversarial"], default=None, help="use a SIMULATED model (offline)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--skip-routing", action="store_true", help="skip the 34-bundle routing confusion (slow)")
    args = ap.parse_args()

    live_provider = os.environ.get("AI_PROVIDER", "none").lower()
    live_key = bool(os.environ.get("GEMINI_API_KEY") if live_provider == "gemini" else os.environ.get("GROQ_API_KEY"))
    work = tempfile.TemporaryDirectory()
    os.environ["DATA_DIR"] = work.name
    os.environ["WORKER_THREADS"] = "0"
    os.environ["APP_ENV"] = "test"
    if args.sim:
        os.environ.update({"AI_PROVIDER": "gemini", "GEMINI_API_KEY": "simulated-key", "AI_FALLBACK_PROVIDER": "none",
                           "AI_DAILY_REQUEST_BUDGET": "100000", "AI_DAILY_PAGE_BUDGET": "1000000"})
        ai_mode = f"simulated-{args.sim}"
    elif live_provider != "none" and live_key:
        ai_mode = "real"
    else:
        ai_mode = "not_run"
    ai_provider_env = os.environ.get("AI_PROVIDER", "none")
    sys.path.insert(0, str(BACKEND))
    from app.config import reset_settings_cache
    reset_settings_cache()
    from unittest.mock import patch
    from app.ai import ground
    from app.ai.client import AIClient
    from app.db import new_id, now_iso, reader, transaction
    from app.main import bootstrap
    from app.pipeline import extract, routing
    from app.pipeline.doctypes import FIELD_LABELS
    from app.security import Principal
    from eval import benchmark
    from synthetic import generator as g, hostile as h, variants as v
    from synthetic.seed import create_application, upload

    import logging
    logging.getLogger("pramaan.ai").setLevel(logging.WARNING)   # one line per call would drown the report
    bootstrap()
    keys: dict[str, str] = {}
    with transaction() as c:
        for iss in ("SYN-FIRE-TS", "SYN-STRUCT"):
            pem, pub = g.issuer_keypair()
            keys[iss] = pem
            c.execute("INSERT INTO issuers VALUES (?,?,?,1,1)", (iss, iss, pub))
    counter = {"n": 0}

    def new_case_app(pid: str, intake: int, reuse_pid: bool = False) -> tuple[Principal, str]:
        """A fresh institution and application; ``reuse_pid`` suffixes the id when several cases print the same one."""
        n = counter["n"] = counter["n"] + 1
        with transaction() as c:
            iid, uid = new_id("ins"), new_id("usr")
            c.execute("INSERT INTO institutions (id,aicte_permanent_id,name,state,trust_name,created_at) VALUES (?,?,?,?,?,?)",
                      (iid, f"{pid}-{n}" if reuse_pid else pid, f"Eval Institute {n} (Synthetic)", "Synthetic", f"Trust {n}",
                       now_iso()))
            c.execute("INSERT INTO aicte_records VALUES (?,?,?,?,1)", (iid, intake, "2025-26", "{}"))
            c.execute("INSERT INTO users (id, email, name, role, institution_id, password_hash, created_at) VALUES"
                      " (?,?,?,?,?,?,?)", (uid, f"e{n}@eval.synthetic", "eval", "INSTITUTION", iid, "x", now_iso()))
        p = Principal(uid, "INSTITUTION", iid, "eval", f"e{n}@eval.synthetic")
        return p, create_application(p)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disclaimer": "Measured on synthetic documents produced by this project's generator; the generator and the extractor "
                      "were built together. Not evidence of accuracy on real AICTE submissions.",
        "environment": {"python": platform.python_version(), "machine": platform.machine(), "repeats": args.repeats},
        "ai": {"mode": ai_mode, "provider": ai_provider_env if ai_mode != "not_run" else "none"},
    }
    if ai_mode.startswith("simulated"):
        report["ai"]["warning"] = ("A SIMULATED model answered, not a real one. These numbers describe the grounding guard "
                                   "(what survives it), not the accuracy of any model.")
    if ai_mode == "not_run":
        report["ai"]["reason"] = "No AI provider with a key is configured in this environment; AI-assisted figures were not measured."

    cases = build_cases(g, v, h, args.repeats)
    labels = dict(FIELD_LABELS)
    sim = Simulator(ai_mode.split("-")[-1], cases, labels) if ai_mode.startswith("simulated") else None
    stack = [patch("app.ai.http.post_json", sim)] if sim else []
    for ctx in stack:   # a simulated run must never reach a real endpoint, not even for the routing bundles
        ctx.start()

    # ------------------------------------------------------------ A. routing confusion on the 34 bundles
    def routing_pass(label: str, suffix: str = "") -> dict[str, Any]:
        confusion: dict[str, Counter] = defaultdict(Counter)
        rows = []
        for n, (fault, rep) in enumerate((f, r) for f in list(benchmark.FAULTS) + benchmark.HARD_NEGATIVES for r in range(args.repeats)):
            intake = [120, 180, 240, 300, 360][n % 5]
            pid = f"1-SYN-R{n:03d}-{rep:04d}{suffix}"
            inst = g.Inst(f"Routing Institute {n} (Synthetic)", pid)
            p, app_id = new_case_app(pid, intake)
            for doc_type, (fname, data) in benchmark._bundle(g, keys, inst, intake, fault).items():
                upload(p, app_id, doc_type, fname, data)
            with reader() as c:
                rec = routing.compute(c, app_id)
            is_fault = fault in benchmark.FAULTS
            expected = ("CORRECTIONS_REQUIRED" if fault in CORRECTIONS_FAULTS else "OFFICER_REVIEW_REQUIRED") if is_fault \
                else "OFFICER_REVIEW_REQUIRED"
            confusion[expected][rec.outcome] += 1
            rows.append({"case": fault, "planted_fault": is_fault, "expected": expected, "predicted": rec.outcome,
                         "reasons": sorted({r["code"] for r in rec.reasons})})
        critical = [r for r in rows if r["planted_fault"] and r["predicted"] == "READY_FOR_SCRUTINY"]
        ready_clean = [r for r in rows if not r["planted_fault"] and r["predicted"] == "READY_FOR_SCRUTINY"]
        return {"label": label, "bundles": len(rows), "planted_fault_bundles": sum(r["planted_fault"] for r in rows),
                "critical_errors_ready_on_planted_fault": len(critical),
                "ready_on_hard_negative": len(ready_clean),
                "exact_match": sum(r["expected"] == r["predicted"] for r in rows),
                "predicted_not_ready_on_every_fault": all(r["predicted"] != "READY_FOR_SCRUTINY" for r in rows if r["planted_fault"]),
                "confusion_expected_by_predicted": {e: {o: confusion[e][o] for o in OUTCOMES} for e in OUTCOMES if confusion[e]},
                "note": "Expected class: CORRECTIONS_REQUIRED when the planted fault raises an institution-owned DEFICIENCY, else "
                        "OFFICER_REVIEW_REQUIRED. Hard negatives are expected to need an officer in this build because every "
                        "verification source is simulated.",
                "cases": rows}

    t0 = time.perf_counter()
    if not args.skip_routing:
        saved = os.environ.get("AI_PROVIDER")
        os.environ["AI_PROVIDER"] = "none"
        report["routing"] = {"ai_off": routing_pass("AI_PROVIDER=none")}
        if saved is not None:
            os.environ["AI_PROVIDER"] = saved
        else:
            os.environ.pop("AI_PROVIDER", None)
        if ai_mode != "not_run":
            report["routing"]["ai_on"] = routing_pass(f"AI on ({ai_mode})", suffix="A")
    report["routing_seconds"] = round(time.perf_counter() - t0, 1)

    # --------------------------------------------------- B. extraction on harder variants (+ hostile documents)
    def norm(value: str | None, vtype: str) -> str | None:
        return None if value is None else ground.canon(value, vtype)

    rec_calls: list[dict[str, Any]] = []

    class Recording(AIClient):
        def extract(self, req, subject_sha, pages):
            outcome = super().extract(req, subject_sha, pages)
            if outcome.result is not None:
                rec_calls.append({"sha": subject_sha, "fields": outcome.result.fields, "cache": outcome.cache_hit,
                                  "latency": outcome.latency_ms, "tokens_in": outcome.result.usage.input_tokens or 0,
                                  "tokens_out": outcome.result.usage.output_tokens or 0, "model": outcome.model, "req": req})
            return outcome

    vtypes = {s.field: s.value_type for specs in extract.TEMPLATES.values() for s in specs}
    results: list[dict[str, Any]] = []
    recorder = patch("app.pipeline.ai_extract.AIClient", Recording)
    stack.append(recorder)
    recorder.start()
    try:
        for case in cases:
            p, app_id = new_case_app(case.truth["permanent_id"], 240, reuse_pid=True)
            fields = list(case.truth)
            det_res = extract.extract_pdf(case.pdf)
            det = {c.field: c.value_norm for c in extract.extract_claims(det_res, case.doc_type)}
            row: dict[str, Any] = {"variant": case.variant, "doc_type": case.doc_type, "hostile": case.hostile, "fields": {}}
            if ai_mode == "not_run":
                final, ai_claims, suggestions = dict(det), {}, []
                doc_id = None
            else:
                doc_id = upload(p, app_id, case.doc_type, "case.pdf", case.pdf)
                with reader() as c:
                    claims = {r["field"]: dict(r) for r in c.execute("SELECT * FROM claims WHERE document_id=?", (doc_id,))}
                    suggestions = [dict(r) for r in c.execute("SELECT * FROM ai_suggestions WHERE document_id=?", (doc_id,))]
                    state = c.execute("SELECT step_status, skip_reason FROM ai_documents WHERE document_id=?", (doc_id,)).fetchone()
                row["ai_step"] = (f"{state['step_status']}:{state['skip_reason']}" if state and state["skip_reason"]
                                  else (state["step_status"] if state else "NOT_RUN"))
                final = {f: cl["value_norm"] for f, cl in claims.items()}
                ai_claims = {f: cl for f, cl in claims.items() if cl["extractor"].startswith("ai+")}
            sha = hashlib.sha256(case.pdf).hexdigest()
            proposals = next((r["fields"] for r in reversed(rec_calls) if r["sha"] == hashlib.sha256(case.pdf).hexdigest()), {})
            pages = ground.pages_from(det_res)
            for f in fields:
                truth = case.truth[f]
                vt = vtypes[f]
                entry: dict[str, Any] = {
                    "truth": truth,
                    "det_correct": (det.get(f) == truth) if truth is not None else (f not in det),
                    "det_missing": f not in det,
                    "final_correct": (final.get(f) == truth) if truth is not None else (f not in final),
                    "ai_claim": f in ai_claims,
                    "ai_claim_wrong": f in ai_claims and (truth is None or ai_claims[f]["value_norm"] != truth),
                    "injected_value_taken": bool(case.injected.get(f) and final.get(f) and
                                                 final.get(f) == norm(case.injected[f], vt)),
                    "suggestion": any(s["field"] == f for s in suggestions),
                }
                prop = proposals.get(f) if proposals else None
                if prop is not None and prop.value:
                    gr = ground.ground(f, vt, prop.value, prop.page, prop.quote, pages)
                    entry["proposed"] = True
                    entry["grounded"] = gr.claim is not None
                    entry["grounded_wrong"] = gr.claim is not None and (truth is None or gr.claim.value_norm != truth)
                else:
                    entry["proposed"] = entry["grounded"] = entry["grounded_wrong"] = False
                row["fields"][f] = entry
            results.append(row)
        # second pass over the same files: the cache should answer every request
        cache_hits = requests_made = 0
        if ai_mode != "not_run":
            before = len(rec_calls)
            for case in cases:
                p, app_id = new_case_app(case.truth["permanent_id"], 240, reuse_pid=True)
                upload(p, app_id, case.doc_type, "case.pdf", case.pdf)
            second = rec_calls[before:]
            cache_hits = sum(1 for r in second if r["cache"])
            requests_made = len(second)
    finally:
        for ctx in reversed(stack):
            ctx.stop()

    def agg(rows: list[tuple[str, str, dict[str, Any]]]) -> dict[str, Any]:
        n = len(rows)
        proposed = [e for _, _, e in rows if e["proposed"]]
        grounded = [e for e in proposed if e["grounded"]]
        ai_claims = [e for _, _, e in rows if e["ai_claim"]]
        out: dict[str, Any] = {
            "n": n,
            "deterministic_accuracy": round(sum(e["det_correct"] for _, _, e in rows) / n, 3),
            "deterministic_missing": sum(e["det_missing"] for _, _, e in rows),
        }
        if ai_mode != "not_run":
            out.update({
                "ai_assisted_accuracy": round(sum(e["final_correct"] for _, _, e in rows) / n, 3),
                "proposals": len(proposed), "grounded": len(grounded),
                "grounding_rate": round(len(grounded) / len(proposed), 3) if proposed else None,
                "suggestion_rate": round(sum(e["suggestion"] for _, _, e in rows) / len(proposed), 3) if proposed else None,
                "ai_claims_created": len(ai_claims), "ai_claims_wrong": sum(e["ai_claim_wrong"] for e in ai_claims),
                "grounded_but_wrong": sum(e["grounded_wrong"] for e in grounded),
                "false_claim_rate": round(sum(e["grounded_wrong"] for e in grounded) / len(grounded), 3) if grounded else 0.0,
                "injected_values_taken": sum(e["injected_value_taken"] for _, _, e in rows)})
        return out

    flat = [(r["doc_type"], f, e) for r in results for f, e in r["fields"].items()]
    per_field = {}
    for dt in sorted({t for t, _, _ in flat}):
        for f in sorted({fl for t, fl, _ in flat if t == dt}):
            per_field[f"{dt}.{f}"] = agg([x for x in flat if x[0] == dt and x[1] == f])
    per_variant = {}
    for var in dict.fromkeys(r["variant"] for r in results):
        per_variant[var] = agg([(r["doc_type"], f, e) for r in results if r["variant"] == var for f, e in r["fields"].items()])
        if ai_mode != "not_run":
            per_variant[var]["ai_step"] = dict(Counter(r.get("ai_step", "NOT_RUN") for r in results if r["variant"] == var))
    report["extraction"] = {"documents": len(results), "per_field": per_field, "per_variant": per_variant, "overall": agg(flat)}
    if ai_mode != "not_run":
        lat = [r["latency"] for r in rec_calls if not r["cache"]]
        report["extraction"]["calls"] = {
            "requests": len(rec_calls), "latency_ms_median": _percentile(lat, 0.5), "latency_ms_p95": _percentile(lat, 0.95),
            "latency_note": "simulated (no network)" if ai_mode.startswith("simulated") else "live round-trip",
            "tokens_in": sum(r["tokens_in"] for r in rec_calls), "tokens_out": sum(r["tokens_out"] for r in rec_calls),
            "second_pass_requests": requests_made, "second_pass_cache_hits": cache_hits}
        hostile_rows = [(r["doc_type"], f, e) for r in results if r["hostile"] for f, e in r["fields"].items()]
        report["injection"] = {
            "hostile_documents": sum(r["hostile"] for r in results),
            "injected_values_taken_as_claims": sum(e["injected_value_taken"] for _, _, e in hostile_rows),
            "ai_claims_wrong_on_hostile": sum(e["ai_claim_wrong"] for _, _, e in hostile_rows)}
    report["cases"] = results

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    summary = {k: v_ for k, v_ in report.items() if k not in ("cases",)}
    if "routing" in summary:
        summary["routing"] = {k: {kk: vv for kk, vv in val.items() if kk != "cases"} for k, val in summary["routing"].items()}
    print(json.dumps(summary, indent=2, default=str))
    print(f"\nreport written to {args.out}")
    work.cleanup()


if __name__ == "__main__":
    main()
