"""Ordered optional pipeline steps. Registration is done once during app import."""
from collections.abc import Callable

_steps: dict[str, list[Callable]] = {"after_fields": [], "after_rules": []}


def register_step(after: str, fn: Callable) -> None:
    if after not in _steps:
        raise ValueError(f"Unknown pipeline hook: {after}")
    if fn not in _steps[after]:
        _steps[after].append(fn)


def run_steps(after, conn, job_id, document_or_application, stage):
    for fn in tuple(_steps[after]):
        fn(conn, job_id, document_or_application, stage)


STAGE_CODES = {
    "Queued": "QUEUED", "Reading file": "READING", "Fingerprinting photograph": "FINGERPRINTING",
    "Extracting text and layout": "EXTRACTING_TEXT", "Extracting fields": "EXTRACTING_FIELDS",
    "Checking document integrity": "INTEGRITY", "Verifying with sources": "VERIFYING",
    "Evaluating rule pack": "RULES", "Re-validating affected rules": "RULES",
    "Done": "DONE", "Failed": "FAILED", "Re-queued after restart": "QUEUED",
}
