"""Document types, classification keywords and field-extraction templates.

Templates follow the layout of publicly posted AICTE EoA letters and common certificate formats.
Every pattern captures the value in a named group ``v`` so its exact position on the page can be
recovered for provenance.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DOC_TYPES: dict[str, str] = {
    "eoa_letter": "Previous Extension of Approval letter",
    "affidavit": "Affidavit (EoA format)",
    "fire_noc": "Fire safety NOC",
    "building_stability": "Structural stability certificate",
    "faculty_summary": "Faculty & student strength summary",
    "infra_photo": "Infrastructure photograph",
}

IMAGE_DOC_TYPES = {"infra_photo"}

FIELD_LABELS: dict[str, str] = {
    "permanent_id": "Permanent ID", "application_ref": "Application ID", "academic_year": "academic year",
    "issue_date": "issue date", "print_date": "print date", "total_intake": "total intake",
    "faculty_count": "number of regular faculty", "student_strength": "student strength",
    "ref_no": "certificate number", "valid_to": "validity date", "built_up_area": "built-up area",
}

# (keyword, weight) — classification is a transparent keyword score, reported with the result.
CLASSIFY_KEYWORDS: dict[str, list[tuple[str, int]]] = {
    "eoa_letter": [("extension of approval", 5), ("approved intake", 3), ("letter printed on", 2), ("file no", 1)],
    "affidavit": [("affidavit", 5), ("deponent", 2), ("intake sought", 3), ("solemnly", 2)],
    "fire_noc": [("fire", 3), ("no objection certificate", 4), ("fire services", 2)],
    "building_stability": [("structural stability", 5), ("built-up area", 2), ("structural engineer", 2)],
    "faculty_summary": [("faculty and student strength", 5), ("student strength", 3), ("regular faculty", 1)],
}

_NUM = r"(?P<v>\d[\d,]*)"
_DATE = r"(?P<v>\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4}|\d{4}-\d{2}-\d{2})"
_AY = r"(?P<v>20\d{2}\s*-\s*(?:20)?\d{2})"
_PID = r"(?P<v>[0-9A-Z]{1,3}-[0-9A-Z-]{4,30})"
_REF = r"(?P<v>[A-Z][A-Z0-9/\-]{5,40})"


@dataclass(frozen=True)
class FieldSpec:
    field: str
    pattern: re.Pattern[str]
    value_type: str  # int | date | academic_year | id | text


def _f(field: str, pattern: str, value_type: str) -> FieldSpec:
    return FieldSpec(field, re.compile(pattern, re.IGNORECASE), value_type)


TEMPLATES: dict[str, list[FieldSpec]] = {
    "eoa_letter": [
        _f("permanent_id", r"permanent\s*id\s*[:\-]?\s*" + _PID, "id"),
        _f("application_ref", r"application\s*id\s*[:\-]?\s*" + _PID, "id"),
        _f("academic_year", r"academic\s+year\s+" + _AY, "academic_year"),
        _f("issue_date", r"(?:^|\s)date\s*[:\-]\s*" + _DATE, "date"),
        _f("print_date", r"letter\s+printed\s+on\s*[:\-]?\s*" + _DATE, "date"),
        _f("total_intake", r"total\s+approved\s+intake\s*[:\-]?\s*" + _NUM, "int"),
    ],
    "affidavit": [
        _f("permanent_id", r"permanent\s*id\s*[:\-]?\s*" + _PID, "id"),
        _f("academic_year", r"academic\s+year\s*[:\-]\s*" + _AY, "academic_year"),
        _f("total_intake", r"total\s+intake\s+sought\s*[:\-]?\s*" + _NUM, "int"),
        _f("faculty_count", r"number\s+of\s+regular\s+faculty\s*[:\-]?\s*" + _NUM, "int"),
        _f("issue_date", r"date\s+of\s+affidavit\s*[:\-]?\s*" + _DATE, "date"),
    ],
    "fire_noc": [
        _f("ref_no", r"certificate\s+no\.?\s*[:\-]?\s*" + _REF, "id"),
        _f("permanent_id", r"permanent\s*id\s*[:\-]?\s*" + _PID, "id"),
        _f("issue_date", r"date\s+of\s+issue\s*[:\-]?\s*" + _DATE, "date"),
        _f("valid_to", r"valid\s+up\s*to\s*[:\-]?\s*" + _DATE, "date"),
    ],
    "building_stability": [
        _f("ref_no", r"certificate\s+no\.?\s*[:\-]?\s*" + _REF, "id"),
        _f("permanent_id", r"permanent\s*id\s*[:\-]?\s*" + _PID, "id"),
        _f("built_up_area", r"built-?up\s+area\s*\(sq\.?\s*m\)\s*[:\-]?\s*" + _NUM, "int"),
        _f("issue_date", r"date\s+of\s+issue\s*[:\-]?\s*" + _DATE, "date"),
        _f("valid_to", r"valid\s+up\s*to\s*[:\-]?\s*" + _DATE, "date"),
    ],
    "faculty_summary": [
        _f("permanent_id", r"permanent\s*id\s*[:\-]?\s*" + _PID, "id"),
        _f("academic_year", r"academic\s+year\s*[:\-]\s*" + _AY, "academic_year"),
        _f("faculty_count", r"number\s+of\s+regular\s+faculty\s*[:\-]?\s*" + _NUM, "int"),
        _f("student_strength", r"total\s+student\s+strength\s*[:\-]?\s*" + _NUM, "int"),
        _f("total_intake", r"total\s+intake\s*[:\-]?\s*" + _NUM, "int"),
    ],
}
