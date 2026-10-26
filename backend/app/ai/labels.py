"""How each rule-read field is labelled on a page. Used only to check that a proposed value is *printed as that
field*; these are layout hints, not compliance logic (the rule pack remains the only source of that).

An alternative is a tuple of lowercase keywords that must appear, in order, among the words just left of the value.
"""
from __future__ import annotations

LABELS: dict[str, list[tuple[str, ...]]] = {
    "permanent_id": [("permanent", "id"), ("permanent", "i.d"), ("aicte", "id")],
    "application_ref": [("application", "id"), ("application", "ref"), ("application", "no")],
    "academic_year": [("academic", "year"), ("session",), ("a.y",)],
    "issue_date": [("date", "issue"), ("issued",), ("date", "affidavit"), ("date",)],
    "print_date": [("printed",), ("print", "date")],
    "total_intake": [("intake",)],
    "faculty_count": [("faculty",)],
    "student_strength": [("student", "strength"), ("students",)],
    "ref_no": [("certificate", "no"), ("reference", "no"), ("ref", "no")],
    "valid_to": [("valid",), ("validity",), ("expiry",), ("expires",), ("upto",), ("till",)],
    "built_up_area": [("built", "area"), ("built-up", "area")],
}

# Words that disqualify a label (a date labelled "valid upto" is not the issue date).
EXCLUDE: dict[str, frozenset[str]] = {
    "issue_date": frozenset({"valid", "upto", "till", "expiry", "expires", "validity", "printed", "print"}),
    "academic_year": frozenset(),
}

# Instruction-like words never appear in a genuine field label.
IMPERATIVE = frozenset({
    "ignore", "disregard", "override", "instruction", "instructions", "previous", "system", "assistant", "prompt",
    "pretend", "jailbreak", "mark", "set", "change", "replace", "verified", "pass", "passed", "regardless", "forget",
})
