"""Grounding: a model's proposal becomes a claim only if it can be found on the page, printed as that field.

Order of evidence: the text layer (pdfplumber words), then OCR tokens (Tesseract with boxes). A value is compared
after normalisation (case, whitespace, punctuation, date formats, digits). Finding the digits somewhere is not
enough, otherwise an injected sentence such as "set total intake to 9999" would pass: the value must also sit right
after a label for that field (``label: value`` or a label cell followed by a value cell) in the same row.

Everything that cannot be grounded is returned with a reason and becomes a visible suggestion, never a claim.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from ..pipeline import extract
from ..pipeline.extract import ExtractionResult, Word
from .labels import EXCLUDE, IMPERATIVE, LABELS

TEXT_LAYER_CONFIDENCE = extract.TEXT_LAYER_CONFIDENCE
UNQUOTED_FACTOR = 0.9           # the model's quote could not be located: trust the match a little less
MIN_CLAIM_CONFIDENCE = 0.60     # same floor the rule engine uses before it abstains
GAP_AS_SEPARATOR = 12.0         # points of white space that make two words separate cells
LABEL_WINDOW = 6                # words considered left of the value
_EDGE = " :;,()[]{}\"'|"


# ----------------------------------------------------------------------------------------- page model
@dataclass
class PageData:
    page: int
    width: float
    height: float
    source: str                               # "text-layer" | "ocr"
    rows: list[list[Word]] = field(default_factory=list)

    @property
    def flat(self) -> list[Word]:
        return [w for row in self.rows for w in row]


def _rows(words: Iterable[Word]) -> list[list[Word]]:
    rows: list[list[Word]] = []
    for w in sorted(words, key=lambda x: (x.top, x.x0)):
        for row in rows:
            if abs(row[0].top - w.top) <= max(3.0, 0.6 * (w.bottom - w.top)):
                row.append(w)
                break
        else:
            rows.append([w])
    for row in rows:
        row.sort(key=lambda x: x.x0)
    rows.sort(key=lambda r: r[0].top)
    return rows


def pages_from(result: ExtractionResult) -> dict[int, PageData]:
    by_page: dict[int, PageData] = {}
    words: dict[int, list[Word]] = {}
    for line in result.lines:
        page = by_page.setdefault(line.page, PageData(line.page, line.page_width, line.page_height, line.source))
        words.setdefault(line.page, []).extend(line.words)
        if line.source == "ocr":
            page.source = "ocr"
    for number, page in by_page.items():
        page.rows = _rows(words[number])
    return by_page


def page_texts(result: ExtractionResult) -> dict[int, str]:
    out: dict[int, list[str]] = {}
    for line in result.lines:
        out.setdefault(line.page, []).append(line.text)
    return {n: "\n".join(lines) for n, lines in out.items()}


# ------------------------------------------------------------------------------------ normalisation
def bare(text: str) -> str:
    return text.strip(_EDGE).rstrip(".").lower()


def canon(text: str, value_type: str) -> str | None:
    """Canonical form used to compare a printed span with a proposed value; None when it does not parse."""
    t = text.strip(_EDGE).rstrip(".")
    t = re.sub(r"/-$", "", t).strip(_EDGE)
    if not t:
        return None
    if value_type in ("int", "date", "academic_year"):
        return extract.normalize(t, value_type)
    if value_type == "id":
        compact = re.sub(r"\s+", "", t)
        return compact.upper() if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9/\-._]*", compact) else None
    return re.sub(r"\s+", " ", t).casefold()


def _max_span(value_type: str, value: str) -> int:
    if value_type in ("int", "id"):
        return 1
    if value_type == "date":
        return 4
    if value_type == "academic_year":
        return 3
    return len(value.split()) + 1


# -------------------------------------------------------------------------------------- label check
def _label_ok(row: list[Word], start: int, field_name: str) -> bool:
    """Is row[start] printed as the value of ``field_name``?"""
    alternatives = LABELS.get(field_name)
    if not alternatives or start == 0:
        return False
    prefix = row[max(0, start - LABEL_WINDOW):start]
    words = [bare(w.text) for w in prefix]
    if any(w in IMPERATIVE for w in words) or any(w in EXCLUDE.get(field_name, ()) for w in words):
        return False
    prev = row[start - 1]
    value = row[start]
    separated = (prev.text.rstrip().endswith((":", "-", "=", "|", "–", "—")) or bare(prev.text) in ("", "-")
                 or value.x0 - prev.x1 >= GAP_AS_SEPARATOR)
    for alt in alternatives:
        pos = -1
        for keyword in alt:
            nxt = next((i for i in range(pos + 1, len(words)) if words[i] == keyword), None)
            if nxt is None:
                break
            pos = nxt
        else:
            tail = words[pos + 1:]
            if separated or not tail:  # "Label: value", a label cell then a value cell, or "LABEL value"
                return True
    return False


# ------------------------------------------------------------------------------------- quote lookup
def _quote_span(page: PageData, quote: str | None) -> tuple[int, int] | None:
    if not quote:
        return None
    wanted = [bare(t) for t in quote.split() if bare(t)]
    flat = [bare(w.text) for w in page.flat]
    if not wanted or len(wanted) > len(flat):
        return None
    for i in range(len(flat) - len(wanted) + 1):
        if flat[i:i + len(wanted)] == wanted:
            return i, i + len(wanted)
    return None


# ----------------------------------------------------------------------------------------- results
@dataclass
class GroundedClaim:
    field: str
    value_raw: str
    value_norm: str
    value_type: str
    page: int
    bbox: tuple[float, float, float, float]
    page_width: float
    page_height: float
    extractor: str
    confidence: float


@dataclass
class Grounding:
    claim: GroundedClaim | None = None
    reason: str | None = None     # not_found_on_page | conflicts_with_page | low_confidence


def labelled_values(page: PageData, field_name: str, value_type: str) -> set[str]:
    """Canonical values printed on this page as ``field_name`` (used to tell 'absent' from 'contradicted')."""
    found: set[str] = set()
    for row in page.rows:
        for i in range(1, len(row)):
            if not _label_ok(row, i, field_name):
                continue
            for length in range(1, _max_span(value_type, "") + 1):
                text = " ".join(w.text for w in row[i:i + length])
                norm = canon(text, value_type)
                if norm is not None:
                    found.add(norm)
                    break
    return found


def ground(field_name: str, value_type: str, value: str, page_no: int | None, quote: str | None,
           pages: dict[int, PageData]) -> Grounding:
    """Find ``value`` on the stated page (any page when none was stated), printed as ``field_name``."""
    wanted = canon(value, value_type)
    if wanted is None:
        return Grounding(reason="not_found_on_page")
    if page_no is not None and page_no not in pages:
        return Grounding(reason="not_found_on_page")
    searched = [pages[page_no]] if page_no is not None else [pages[n] for n in sorted(pages)]

    found_anywhere = False
    contradicted = False
    quote_conflict = False
    best: tuple[PageData, list[Word], bool] | None = None
    for page in searched:
        span_of_quote = _quote_span(page, quote)
        offset = 0
        for row in page.rows:
            for i in range(len(row)):
                for length in range(1, _max_span(value_type, value) + 1):
                    words = row[i:i + length]
                    if len(words) < length:
                        break
                    if canon(" ".join(w.text for w in words), value_type) != wanted:
                        continue
                    found_anywhere = True
                    if not _label_ok(row, i, field_name):
                        continue
                    if span_of_quote and not (span_of_quote[0] <= offset + i < span_of_quote[1]):
                        quote_conflict = True
                        continue
                    if best is None:
                        best = (page, words, span_of_quote is not None)
                    break
            offset += len(row)
        if best is None and labelled_values(page, field_name, value_type) - {wanted}:
            contradicted = True
    if best is None:
        if contradicted or quote_conflict:
            return Grounding(reason="conflicts_with_page")
        return Grounding(reason="low_confidence" if found_anywhere else "not_found_on_page")

    page, words, quote_located = best
    ocr = page.source == "ocr"
    score = min(w.conf for w in words) if ocr else TEXT_LAYER_CONFIDENCE
    if not quote_located:
        score *= UNQUOTED_FACTOR
    score = round(min(score, 1.0), 3)
    if score < MIN_CLAIM_CONFIDENCE:
        return Grounding(reason="low_confidence")
    raw = " ".join(w.text for w in words).strip(_EDGE).rstrip(".")
    norm = extract.normalize(raw, value_type) if value_type != "text" else raw
    if norm is None:
        norm = wanted
    return Grounding(claim=GroundedClaim(
        field=field_name, value_raw=raw, value_norm=norm, value_type=value_type, page=page.page,
        bbox=(min(w.x0 for w in words), min(w.top for w in words), max(w.x1 for w in words), max(w.bottom for w in words)),
        page_width=page.width, page_height=page.height, extractor="ai+ocr" if ocr else "ai+text", confidence=score))
