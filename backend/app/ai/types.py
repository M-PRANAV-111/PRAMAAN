"""Request/result types, the response schemas models must satisfy, and the error taxonomy."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

DOC_TYPE_CHOICES = ("eoa_letter", "affidavit", "fire_noc", "building_stability", "faculty_summary", "infra_photo", "other")


# ------------------------------------------------------------------------------------------- errors
class AIError(Exception):
    """Base class. ``code`` is the only text that may reach logs or the job notes."""
    code = "ai_error"

    def __init__(self, code: str | None = None):
        super().__init__(code or self.code)
        if code:
            self.code = code


class NotAvailable(AIError):
    code = "not_available"


class MissingKey(AIError):
    code = "no_api_key"


class RateLimited(AIError):
    code = "rate_limited"


class Unavailable(AIError):
    code = "unavailable"


class AuthError(AIError):
    code = "auth"


class BadRequest(AIError):
    code = "bad_request"


class SchemaViolation(AIError):
    code = "schema_violation"


# ------------------------------------------------------------------------------ response schemas
class FieldProposal(BaseModel):
    """One proposed field value. Length limits are enforced here because structured output ignores them."""
    model_config = ConfigDict(extra="forbid")
    value: str | None = Field(default=None, max_length=200)
    page: int | None = Field(default=None, ge=1, le=500)
    quote: str | None = Field(default=None, max_length=400)


def extraction_model(doc_type: str, field_names: list[str]) -> type[BaseModel]:
    """One model per document type holding exactly the requested fields, all required (null when unsure)."""
    definitions: dict[str, Any] = {name: (FieldProposal, ...) for name in field_names}
    return create_model(f"Extract_{doc_type}", __config__=ConfigDict(extra="forbid"), **definitions)


class ClassifyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Literal["eoa_letter", "affidavit", "fire_noc", "building_stability", "faculty_summary",
                           "infra_photo", "other"]
    confidence: float = Field(ge=0, le=1)
    evidence_quote: str | None = Field(default=None, max_length=300)


class ExplainResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=700)


# ------------------------------------------------------------------------------------ requests
@dataclass(frozen=True)
class FieldInfo:
    name: str
    label: str
    value_type: str


@dataclass
class ExtractRequest:
    doc_type: str
    doc_label: str
    fields: list[FieldInfo]
    pdf_bytes: bytes | None = None          # vision-capable providers read the pages natively
    page_numbers: list[int] = field(default_factory=list)
    page_text: dict[int, str] = field(default_factory=dict)   # text-only providers read this instead


@dataclass
class ClassifyRequest:
    expected_type: str
    labels: dict[str, str]
    pdf_bytes: bytes | None = None
    page_numbers: list[int] = field(default_factory=list)
    page_text: dict[int, str] = field(default_factory=dict)


@dataclass
class ExplainRequest:
    facts: dict[str, Any]
    language: str = "en"


# -------------------------------------------------------------------------------------- results
@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0


@dataclass
class ProviderResult:
    """A validated response. ``response`` is always a Pydantic instance; ``available=False`` means 'not available'."""
    available: bool = True
    response: BaseModel | None = None
    usage: Usage = field(default_factory=Usage)
    provider: str = "none"
    model: str = ""

    def payload(self) -> dict[str, Any]:
        return self.response.model_dump() if self.response is not None else {}


class ExtractResult(ProviderResult):
    @property
    def fields(self) -> dict[str, FieldProposal]:
        if self.response is None:
            return {}
        return {name: FieldProposal.model_validate(value) for name, value in self.response.model_dump().items()}


class ClassifyResult(ProviderResult):
    @property
    def document_type(self) -> str | None:
        return self.response.document_type if isinstance(self.response, ClassifyResponse) else None

    @property
    def confidence(self) -> float:
        return self.response.confidence if isinstance(self.response, ClassifyResponse) else 0.0

    @property
    def evidence_quote(self) -> str | None:
        return self.response.evidence_quote if isinstance(self.response, ClassifyResponse) else None


class ExplainResult(ProviderResult):
    @property
    def text(self) -> str:
        return self.response.text if isinstance(self.response, ExplainResponse) else ""
