"""Text-layer and OCR extraction with positional provenance.

Coordinates are PDF points with the origin at the top-left of the page (x right, y down), which is
what the evidence viewer overlays on rendered page images.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

import pdfplumber
import pypdfium2 as pdfium
import pytesseract
from PIL import Image

from ..config import get_settings
from .doctypes import CLASSIFY_KEYWORDS, TEMPLATES

TEXT_LAYER_CONFIDENCE = 0.98
OCR_DPI = 300
MIN_TEXT_CHARS = 20


@dataclass
class Word:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    conf: float = 1.0


@dataclass
class Line:
    page: int
    words: list[Word]
    page_width: float
    page_height: float
    source: str  # "text-layer" | "ocr"

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class ExtractedClaim:
    field: str
    value_raw: str
    value_norm: str | None
    value_type: str
    page: int
    bbox: tuple[float, float, float, float]
    page_width: float
    page_height: float
    extractor: str
    confidence: float


@dataclass
class ExtractionResult:
    lines: list[Line] = field(default_factory=list)
    has_text_layer: bool = False
    used_ocr: bool = False
    pages: int = 0
    detected_type: str | None = None
    classification_scores: dict[str, int] = field(default_factory=dict)
    claims: list[ExtractedClaim] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n".join(l.text for l in self.lines)


def _configure_tesseract() -> None:
    cmd = get_settings().tesseract_cmd
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def _group_lines(words: Iterable[Word], page: int, w: float, h: float, source: str, tol: float = 3.0) -> list[Line]:
    rows: list[list[Word]] = []
    for word in sorted(words, key=lambda x: (round(x.top), x.x0)):
        for row in rows:
            if abs(row[0].top - word.top) <= tol:
                row.append(word)
                break
        else:
            rows.append([word])
    lines = []
    for row in rows:
        row.sort(key=lambda x: x.x0)
        # Split a visual row into separate lines where there is a wide horizontal gap (two-column layouts).
        segment: list[Word] = [row[0]]
        for prev, cur in zip(row, row[1:]):
            if cur.x0 - prev.x1 > 60:
                lines.append(Line(page, segment, w, h, source))
                segment = [cur]
            else:
                segment.append(cur)
        lines.append(Line(page, segment, w, h, source))
    lines.sort(key=lambda l: (l.words[0].top, l.words[0].x0))
    return lines


def render_page(pdf_bytes: bytes, page_index: int, dpi: int = 150) -> Image.Image:
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        page = pdf[page_index]
        image = page.render(scale=dpi / 72).to_pil()
        page.close()
        return image.convert("RGB")
    finally:
        pdf.close()


def ocr_words(image: Image.Image, scale: float) -> list[Word]:
    _configure_tesseract()
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, config="--psm 6")
    words = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(Word(text, x / scale, y / scale, (x + w) / scale, (y + h) / scale, conf / 100.0))
    return words


def extract_pdf(pdf_bytes: bytes) -> ExtractionResult:
    result = ExtractionResult()
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        result.pages = len(pdf.pages)
        for idx, page in enumerate(pdf.pages):
            words = [
                Word(w["text"], float(w["x0"]), float(w["top"]), float(w["x1"]), float(w["bottom"]))
                for w in page.extract_words(keep_blank_chars=False, use_text_flow=False)
            ]
            chars = sum(len(w.text) for w in words)
            if chars >= MIN_TEXT_CHARS:
                result.has_text_layer = True
                result.lines.extend(_group_lines(words, idx + 1, float(page.width), float(page.height), "text-layer"))
            else:
                image = render_page(pdf_bytes, idx, dpi=OCR_DPI)
                scale = OCR_DPI / 72
                ow = ocr_words(image, scale)
                if ow:
                    result.used_ocr = True
                    result.lines.extend(_group_lines(ow, idx + 1, float(page.width), float(page.height), "ocr"))
    result.detected_type, result.classification_scores = classify(result.full_text)
    return result


def classify(text: str) -> tuple[str | None, dict[str, int]]:
    low = text.lower()
    scores = {dt: sum(w for kw, w in kws if kw in low) for dt, kws in CLASSIFY_KEYWORDS.items()}
    best = max(scores, key=lambda k: scores[k]) if scores else None
    if best is None or scores[best] < 4:
        return None, scores
    return best, scores


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def parse_date(raw: str) -> date | None:
    s = raw.strip().replace(",", " ")
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", s)
    if m and m.group(2)[:3].lower() in _MONTHS:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        except ValueError:
            return None
    return None


def normalize(raw: str, value_type: str) -> str | None:
    raw = raw.strip()
    if value_type == "int":
        digits = raw.replace(",", "")
        return str(int(digits)) if digits.isdigit() else None
    if value_type == "date":
        d = parse_date(raw)
        return d.isoformat() if d else None
    if value_type == "academic_year":
        m = re.fullmatch(r"(20\d{2})\s*-\s*(?:20)?(\d{2})", raw)
        return f"{m.group(1)}-{m.group(2)}" if m else None
    if value_type == "id":
        return re.sub(r"\s+", "", raw).upper()
    return raw


def _span_bbox(line: Line, start: int, end: int) -> tuple[tuple[float, float, float, float], float]:
    """Union bbox and minimum confidence of the words overlapping character span [start, end)."""
    pos = 0
    hit: list[Word] = []
    for w in line.words:
        w_start, w_end = pos, pos + len(w.text)
        if w_end > start and w_start < end:
            hit.append(w)
        pos = w_end + 1
    if not hit:
        hit = line.words
    bbox = (min(w.x0 for w in hit), min(w.top for w in hit), max(w.x1 for w in hit), max(w.bottom for w in hit))
    return bbox, min(w.conf for w in hit)


def extract_claims(result: ExtractionResult, doc_type: str) -> list[ExtractedClaim]:
    claims: list[ExtractedClaim] = []
    seen: set[str] = set()
    for spec in TEMPLATES.get(doc_type, []):
        for line in result.lines:
            m = spec.pattern.search(line.text)
            if not m:
                continue
            raw = m.group("v")
            bbox, word_conf = _span_bbox(line, m.start("v"), m.end("v"))
            norm = normalize(raw, spec.value_type)
            if line.source == "text-layer":
                conf, extractor = TEXT_LAYER_CONFIDENCE, "text-layer+template"
            else:
                conf, extractor = round(word_conf, 3), "ocr+template"
            if norm is None:
                conf = min(conf, 0.3)  # matched the label but the value did not parse
            if spec.field in seen:
                continue
            seen.add(spec.field)
            claims.append(ExtractedClaim(spec.field, raw, norm, spec.value_type, line.page, bbox,
                                         line.page_width, line.page_height, extractor, conf))
            break
    result.claims = claims
    return claims


def today() -> date:
    return datetime.now().date()
