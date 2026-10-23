"""Data policy, enforced in code: under ``AI_DATA_POLICY=synthetic_only`` (the default) a document may reach an
external provider only if its own extracted text carries the SYNTHETIC stamp line that ``backend/synthetic`` prints
on every generated page.

The institution name does not count: a real file could be uploaded under a demo institution. A watermark word
alone does not count either; the full stamp phrase must be present on every page that would be sent. Otherwise the
AI step is skipped with reason ``data_policy`` and the deterministic pipeline continues unchanged.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .config import AIConfig

_STAMP = "SYNTHETICNOTAREALDOCUMENT"
_LETTERS = re.compile(r"[^A-Z]")


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str | None = None


def page_has_stamp(text: str, ocr: bool = False) -> bool:
    """True when the stamp phrase is on the page. OCR output gets a small edit-distance tolerance."""
    squeezed = _LETTERS.sub("", (text or "").upper())
    if _STAMP in squeezed:
        return True
    if not ocr or len(squeezed) < len(_STAMP) - 4:
        return False
    size = len(_STAMP)
    for start in range(0, max(1, len(squeezed) - size + 5)):
        window = squeezed[start:start + size]
        if difflib.SequenceMatcher(None, window, _STAMP).ratio() >= 0.9:
            return True
    return False


def decide(cfg: AIConfig, page_texts: dict[int, str], ocr_pages: set[int] | frozenset[int] = frozenset()) -> Decision:
    """May these pages be sent to an external provider?"""
    if cfg.data_policy == "allow_real":
        return Decision(True)
    if not page_texts:
        return Decision(False, "data_policy")
    for page, text in page_texts.items():
        if not page_has_stamp(text, ocr=page in ocr_pages):
            return Decision(False, "data_policy")
    return Decision(True)
