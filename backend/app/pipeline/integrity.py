"""Explainable document-integrity indicators.

These are review signals, not verdicts. Re-saving, scanning, signing and format conversion can all
produce them legitimately, so every indicator is worded as "requires verification" and the engine
abstains (reports nothing) when it cannot read a value reliably.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pikepdf
import pytesseract
from PIL import ImageOps

from .doctypes import FIELD_LABELS
from .extract import ExtractedClaim, normalize, render_page, _configure_tesseract

RENDER_DPI = 300
OCR_MIN_CONFIDENCE = 0.75


@dataclass
class Indicator:
    kind: str
    title: str
    detail: dict[str, Any]
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None


def _pdf_date(value: Any) -> datetime | None:
    if value is None:
        return None
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?", str(value))
    if not m:
        return None
    parts = [int(p) if p else 0 for p in m.groups()]
    try:
        return datetime(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])
    except ValueError:
        return None


def structure_indicators(pdf_bytes: bytes) -> tuple[list[Indicator], dict[str, Any]]:
    indicators: list[Indicator] = []
    facts: dict[str, Any] = {}
    eof_markers = len(re.findall(rb"%%EOF", pdf_bytes))
    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        linearized = bool(pdf.is_linearized)
        info = pdf.docinfo
        producer = str(info.get("/Producer", "")) or None
        created = _pdf_date(info.get("/CreationDate"))
        modified = _pdf_date(info.get("/ModDate"))
        has_signature = any(
            str(f.get("/FT", "")) == "/Sig" for f in (pdf.Root.get("/AcroForm", {}) or {}).get("/Fields", [])
        ) if "/AcroForm" in pdf.Root else False
    incremental_saves = max(0, eof_markers - 1 - (1 if linearized else 0))
    facts.update({"eof_markers": eof_markers, "linearized": linearized, "incremental_saves": incremental_saves,
                  "producer": producer, "created": created.isoformat() if created else None,
                  "modified": modified.isoformat() if modified else None, "has_signature_field": has_signature})
    if incremental_saves > 0:
        indicators.append(Indicator(
            "INCREMENTAL_UPDATE",
            "File was modified after it was first produced",
            {"incremental_saves": incremental_saves,
             "note": "Legitimate for digitally signed or annotated files; check what changed in the later revision.",
             "signature_field_present": has_signature},
        ))
    if created and modified and modified < created:
        indicators.append(Indicator(
            "DATE_ORDER",
            "Modification date precedes creation date in file metadata",
            {"created": created.isoformat(), "modified": modified.isoformat()},
        ))
    return indicators, facts


def visible_text_indicators(pdf_bytes: bytes, claims: list[ExtractedClaim]) -> tuple[list[Indicator], list[dict[str, Any]]]:
    """Compare text-layer values with what OCR reads in the same rendered region."""
    _configure_tesseract()
    checks: list[dict[str, Any]] = []
    indicators: list[Indicator] = []
    candidates = [c for c in claims if c.extractor.startswith("text-layer") and c.value_norm is not None
                  and (c.value_type == "int" or (c.value_type == "date" and re.fullmatch(r"[\d\-/.]+", c.value_raw)))]
    renders: dict[int, Any] = {}
    scale = RENDER_DPI / 72
    for c in candidates:
        if c.page not in renders:
            renders[c.page] = render_page(pdf_bytes, c.page - 1, dpi=RENDER_DPI)
        img = renders[c.page]
        x0, y0, x1, y1 = c.bbox
        pad = 2.5
        box = (max(0, int((x0 - pad) * scale)), max(0, int((y0 - pad) * scale)),
               min(img.width, int((x1 + pad) * scale)), min(img.height, int((y1 + pad) * scale)))
        crop = ImageOps.expand(ImageOps.grayscale(img.crop(box)), border=20, fill=255)
        whitelist = "0123456789," if c.value_type == "int" else "0123456789-/."
        data = pytesseract.image_to_data(crop, output_type=pytesseract.Output.DICT,
                                         config=f"--psm 7 -c tessedit_char_whitelist={whitelist}")
        words = [(t.strip(), float(cf)) for t, cf in zip(data["text"], data["conf"]) if t.strip() and float(cf) >= 0]
        seen_raw = "".join(t for t, _ in words)
        conf = min((cf for _, cf in words), default=0.0) / 100.0
        seen_norm = normalize(seen_raw, c.value_type) if seen_raw else None
        record = {"field": c.field, "page": c.page, "text_layer": c.value_raw, "rendered_ocr": seen_raw or None,
                  "ocr_confidence": round(conf, 3)}
        if seen_norm is None or conf < OCR_MIN_CONFIDENCE:
            record["outcome"] = "ABSTAINED"
        elif seen_norm == c.value_norm:
            record["outcome"] = "MATCH"
        else:
            record["outcome"] = "MISMATCH"
            indicators.append(Indicator(
                "VISIBLE_TEXT_MISMATCH",
                f"Visible {FIELD_LABELS.get(c.field, c.field)} differs from the embedded text",
                {"field": c.field, "embedded_text": c.value_raw, "visible_text": seen_raw,
                 "ocr_confidence": round(conf, 3),
                 "note": "Typical of an overlay edit; can also come from re-rendering. Compare with the issuer copy."},
                page=c.page, bbox=c.bbox,
            ))
        checks.append(record)
    return indicators, checks
