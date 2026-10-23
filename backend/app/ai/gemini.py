"""Gemini adapter over plain HTTPS (no SDK). Every request detail lives in this file.

Request shape, per the Gemini API docs checked on 2026-10-23 (ai.google.dev: Interactions API, Structured outputs,
Document processing):

    POST https://generativelanguage.googleapis.com/v1beta/interactions
    x-goog-api-key: <key>
    {"model": ..., "system_instruction": ..., "input": [{"type": "document", "data": <base64 pdf>,
     "mime_type": "application/pdf"}, {"type": "text", "text": ...}],
     "response_format": {"type": "text", "mime_type": "application/json", "schema": {...}},
     "generation_config": {...}, "store": false}

The reply carries ``steps``; the model text is in the last ``model_output`` step's ``text`` content parts and token
counts are in ``usage``. Structured output ignores length keywords, so the response is always re-validated here.
"""
from __future__ import annotations

import base64
import json
import re
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from . import http, prompts
from .schema_util import to_schema
from .types import (ClassifyRequest, ClassifyResponse, ClassifyResult, ExplainRequest, ExplainResponse, ExplainResult,
                    ExtractRequest, ExtractResult, MissingKey, NotAvailable, ProviderResult, SchemaViolation, Unavailable,
                    Usage, extraction_model)

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float = 45.0, max_output_tokens: int = 1500):
        self._key = api_key
        self.model = model
        self._timeout = timeout
        self._max_tokens = max_output_tokens

    # ------------------------------------------------------------------ tasks
    def extract(self, req: ExtractRequest) -> ExtractResult:
        model = extraction_model(req.doc_type, [f.name for f in req.fields])
        parts = self._document_parts(req.pdf_bytes, req.page_text, prompts.extract_task(req))
        return self._run(ExtractResult, model, prompts.EXTRACT_SYSTEM, parts)

    def classify(self, req: ClassifyRequest) -> ClassifyResult:
        parts = self._document_parts(req.pdf_bytes, req.page_text, prompts.classify_task(req))
        return self._run(ClassifyResult, ClassifyResponse, prompts.CLASSIFY_SYSTEM, parts)

    def explain(self, req: ExplainRequest) -> ExplainResult:
        parts = [{"type": "text", "text": prompts.explain_task(req)}]
        return self._run(ExplainResult, ExplainResponse, prompts.EXPLAIN_SYSTEM, parts)

    # ---------------------------------------------------------------- plumbing
    @staticmethod
    def _document_parts(pdf: bytes | None, page_text: dict[int, str], task: str) -> list[dict[str, Any]]:
        if pdf:
            # Document first, instructions after it (the documented order for a single document).
            return [{"type": "document", "data": base64.b64encode(pdf).decode("ascii"), "mime_type": "application/pdf"},
                    {"type": "text", "text": task}]
        if page_text:
            return [{"type": "text", "text": prompts.text_user_message(task, page_text)}]
        raise NotAvailable("no_input")

    def _run(self, result_cls: type[ProviderResult], schema_model: type[BaseModel], system: str,
             parts: list[dict[str, Any]]) -> Any:
        if not self._key:
            raise MissingKey()
        payload = {
            "model": self.model,
            "system_instruction": system,
            "input": parts,
            "response_format": {"type": "text", "mime_type": "application/json", "schema": to_schema(schema_model, "gemini")},
            "generation_config": {"max_output_tokens": self._max_tokens, "thinking_level": "minimal"},
            "store": False,
        }
        started = time.monotonic()
        body = http.post_json(API_URL, {"x-goog-api-key": self._key, "Content-Type": "application/json"}, payload,
                              self._timeout)
        latency = int((time.monotonic() - started) * 1000)
        text = self._output_text(body)
        try:
            validated = schema_model.model_validate(json.loads(_FENCE.sub("", text.strip())))
        except (ValueError, ValidationError):
            raise SchemaViolation() from None
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        return result_cls(available=True, response=validated, provider=self.name, model=self.model,
                          usage=Usage(_int(usage.get("total_input_tokens")), _int(usage.get("total_output_tokens")), latency))

    @staticmethod
    def _output_text(body: dict[str, Any]) -> str:
        status = body.get("status")
        if status is not None and status != "completed":
            raise SchemaViolation(f"status_{status}")  # e.g. "incomplete": truncated JSON must not be trusted
        for step in reversed(body.get("steps") or []):
            if isinstance(step, dict) and step.get("type") == "model_output":
                text = "".join(p.get("text", "") for p in step.get("content") or []
                               if isinstance(p, dict) and p.get("type") == "text")
                if text:
                    return text
        if body.get("errors"):
            raise Unavailable("provider_error")
        raise SchemaViolation("no_output")


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
