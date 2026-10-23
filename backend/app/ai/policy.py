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
_GRAM = 5            # OCR errors are local, so some 5-letter piece of the stamp usually survives
_MAX_WINDOWS = 64    # bounds the cost on a dense page that does not carry the stamp


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
    starts: set[int] = set()
    for k in range(len(_STAMP) - _GRAM + 1):  # candidate windows are anchored on pieces of the stamp that survived
        gram, at = _STAMP[k:k + _GRAM], squeezed.find(_STAMP[k:k + _GRAM])
        while at != -1 and len(starts) < _MAX_WINDOWS:
            starts.add(max(0, at - k))
            at = squeezed.find(gram, at + 1)
    return any(difflib.SequenceMatcher(None, squeezed[s:s + len(_STAMP)], _STAMP).ratio() >= 0.9 for s in starts)


def stamp_status(page_texts: dict[int, str], ocr_pages: set[int] | frozenset[int] = frozenset()) -> bool:
    """Do all these pages carry the stamp? (An empty set of pages does not.)"""
    return bool(page_texts) and all(page_has_stamp(text, ocr=page in ocr_pages) for page, text in page_texts.items())


def decide(cfg: AIConfig, page_texts: dict[int, str], ocr_pages: set[int] | frozenset[int] = frozenset()) -> Decision:
    """May these pages be sent to an external provider?"""
    if cfg.data_policy == "allow_real":
        return Decision(True)
    return Decision(True) if stamp_status(page_texts, ocr_pages) else Decision(False, "data_policy")
