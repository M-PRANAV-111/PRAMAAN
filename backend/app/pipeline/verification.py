"""Verification ladder: try the strongest available channel first, record every attempt.

Tier 1  Signed QR (Ed25519)          — real cryptographic check against registered issuer keys.
Tier 2  AICTE institutional records  — simulated table standing in for an authorized interface.
Tier 3  Issuer registry by reference — simulated; availability configurable per issuer.
Tier 4  Manual                       — officer confirms.

Adapters never call the network unless an integration is configured and authorized; in this build
none is, and every simulated result is stored with ``simulated = 1``.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

import cv2
import numpy as np
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .extract import render_page

QR_PREFIX = "PRAMAAN-SQR1"
DECISIVE = {"VERIFIED", "MISMATCH_DETECTED", "EXPIRED"}


@dataclass
class Attempt:
    tier: int
    channel: str
    status: str
    simulated: bool
    request_ref: str | None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def response_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.detail, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class LadderContext:
    conn: sqlite3.Connection
    doc_type: str
    pdf_bytes: bytes | None
    claims: dict[str, str | None]  # field -> normalized value
    institution: dict[str, Any]
    record: dict[str, Any] | None
    academic_year_start: date


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def decode_qr(pdf_bytes: bytes) -> str | None:
    """Try several detectors and resolutions; QR decoding is the most brittle step in the ladder."""
    detectors = [cv2.QRCodeDetectorAruco(), cv2.QRCodeDetector()]
    for dpi in (200, 300):
        img = cv2.cvtColor(np.asarray(render_page(pdf_bytes, 0, dpi=dpi)), cv2.COLOR_RGB2BGR)
        h, w = img.shape[:2]
        for view in (img, img[h // 2:, w // 2:]):
            for det in detectors:
                text = det.detectAndDecode(view)[0]
                if text:
                    return text
    return None


def _compare(expected: dict[str, Any], claims: dict[str, str | None]) -> dict[str, dict[str, Any]]:
    diffs = {}
    for f, exp in expected.items():
        got = claims.get(f)
        if got is None:
            continue
        if str(exp).upper() != str(got).upper():
            diffs[f] = {"source": exp, "document": got}
    return diffs


def tier_signed_qr(ctx: LadderContext) -> Attempt | None:
    if ctx.pdf_bytes is None:
        return None
    text = decode_qr(ctx.pdf_bytes)
    if not text or not text.startswith(QR_PREFIX + "."):
        return None
    try:
        _, payload_b64, sig_b64 = text.split(".")
        payload_bytes = _b64d(payload_b64)
        payload = json.loads(payload_bytes)
    except (ValueError, json.JSONDecodeError):
        return Attempt(1, "signed_qr", "MISMATCH_DETECTED", False, None, {"reason": "QR present but payload unreadable"})
    issuer = ctx.conn.execute("SELECT * FROM issuers WHERE id = ?", (payload.get("iss"),)).fetchone()
    ref = payload.get("ref")
    if issuer is None:
        return Attempt(1, "signed_qr", "MANUAL_REVIEW_REQUIRED", False, ref,
                       {"reason": "QR signed by an issuer whose key is not registered", "issuer": payload.get("iss")})
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(issuer["public_key_b64"])).verify(_b64d(sig_b64), payload_bytes)
    except (InvalidSignature, ValueError):
        return Attempt(1, "signed_qr", "MISMATCH_DETECTED", False, ref,
                       {"reason": "QR signature does not verify with the issuer's public key", "issuer": issuer["id"]})
    expected = {k: payload[k] for k in ("ref_no", "permanent_id", "valid_to") if k in payload}
    diffs = _compare(expected, ctx.claims)
    base = {"issuer": issuer["id"], "issuer_name": issuer["name"], "signed_fields": expected,
            "issuer_key_simulated": bool(issuer["simulated"])}
    if diffs:
        return Attempt(1, "signed_qr", "MISMATCH_DETECTED", False, ref,
                       {**base, "reason": "Signed QR is authentic but the printed values differ", "differences": diffs})
    vt = payload.get("valid_to")
    if vt and date.fromisoformat(vt) < ctx.academic_year_start:
        return Attempt(1, "signed_qr", "EXPIRED", False, ref, {**base, "reason": "Authentic, but validity ends before the academic year starts"})
    return Attempt(1, "signed_qr", "VERIFIED", False, ref, {**base, "reason": "Signature valid and printed values match the signed values"})


def tier_aicte_record(ctx: LadderContext) -> Attempt | None:
    if ctx.doc_type != "eoa_letter":
        return None
    if ctx.record is None:
        return Attempt(2, "aicte_records", "SOURCE_UNAVAILABLE", True, ctx.institution["aicte_permanent_id"],
                       {"reason": "No AICTE record available for this institution"})
    expected = {"permanent_id": ctx.institution["aicte_permanent_id"], "total_intake": str(ctx.record["approved_intake"])}
    diffs = _compare(expected, ctx.claims)
    detail = {"record_fields": expected, "note": "AICTE records take precedence over a printed letter."}
    if diffs:
        return Attempt(2, "aicte_records", "MISMATCH_DETECTED", True, ctx.institution["aicte_permanent_id"],
                       {**detail, "reason": "Letter differs from AICTE records", "differences": diffs})
    return Attempt(2, "aicte_records", "VERIFIED", True, ctx.institution["aicte_permanent_id"],
                   {**detail, "reason": "Letter matches AICTE records"})


def tier_issuer_registry(ctx: LadderContext) -> Attempt | None:
    ref = ctx.claims.get("ref_no")
    if ctx.doc_type not in {"fire_noc", "building_stability"} or not ref:
        return None
    row = ctx.conn.execute(
        "SELECT r.*, i.name AS issuer_name, i.registry_available FROM issuer_registry r JOIN issuers i ON i.id = r.issuer_id"
        " WHERE r.ref_no = ?", (ref,)).fetchone()
    if row is not None and not row["registry_available"]:
        return Attempt(3, "issuer_registry", "SOURCE_UNAVAILABLE", True, ref,
                       {"reason": "Issuer registry did not respond", "issuer": row["issuer_id"]})
    if row is None:
        return Attempt(3, "issuer_registry", "MANUAL_REVIEW_REQUIRED", True, ref,
                       {"reason": "Reference number not found in the issuer registry; confirm with the issuer"})
    fields = json.loads(row["fields_json"])
    diffs = _compare(fields, ctx.claims)
    detail = {"issuer": row["issuer_id"], "issuer_name": row["issuer_name"], "registry_fields": fields}
    if diffs:
        return Attempt(3, "issuer_registry", "MISMATCH_DETECTED", True, ref,
                       {**detail, "reason": "Registry entry differs from the document", "differences": diffs})
    vt = fields.get("valid_to")
    if vt and date.fromisoformat(vt) < ctx.academic_year_start:
        return Attempt(3, "issuer_registry", "EXPIRED", True, ref, {**detail, "reason": "Registry confirms the document; validity has ended"})
    return Attempt(3, "issuer_registry", "VERIFIED", True, ref, {**detail, "reason": "Registry entry matches the document"})


LADDERS: dict[str, list[Callable[[LadderContext], Attempt | None]]] = {
    "fire_noc": [tier_signed_qr, tier_issuer_registry],
    "building_stability": [tier_signed_qr, tier_issuer_registry],
    "eoa_letter": [tier_aicte_record],
}


def run_ladder(ctx: LadderContext) -> tuple[str | None, list[Attempt]]:
    """Returns (final_status, attempts). ``None`` means the document type is a declaration with no source."""
    ladder = LADDERS.get(ctx.doc_type)
    if not ladder:
        return None, []
    attempts: list[Attempt] = []
    for tier in ladder:
        attempt = tier(ctx)
        if attempt is None:
            continue
        attempts.append(attempt)
        if attempt.status in DECISIVE:
            return attempt.status, attempts
    if any(a.status == "SOURCE_UNAVAILABLE" for a in attempts):
        final = "SOURCE_UNAVAILABLE"
    else:
        final = "MANUAL_REVIEW_REQUIRED"
    attempts.append(Attempt(4, "manual", "MANUAL_REVIEW_REQUIRED", False, None,
                            {"reason": "No automated channel was decisive; an officer must confirm with the issuer"}))
    return final, attempts
