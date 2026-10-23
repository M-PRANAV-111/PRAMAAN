"""Groq adapter: text only. The published model table lists no vision model, so it reads the locally extracted
text (text layer or Tesseract output) of the pages in question and answers with the same schema.

    POST https://api.groq.com/openai/v1/chat/completions   (Authorization: Bearer <key>)
    {"model": "openai/gpt-oss-120b", "messages": [...], "temperature": 0,
     "response_format": {"type": "json_schema", "json_schema": {"name": ..., "strict": true, "schema": {...}}}}

Free-plan base limits for this model (checked 2026-10-23): 30 requests/min, 1K/day, 8K tokens/min, 200K tokens/day.
The shared client enforces a daily request budget well below that; the per-minute limits surface as HTTP 429.
"""
from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from . import http, prompts
from .schema_util import to_schema
from .types import (ClassifyRequest, ClassifyResponse, ClassifyResult, ExplainRequest, ExplainResponse, ExplainResult,
                    ExtractRequest, ExtractResult, MissingKey, NotAvailable, ProviderResult, SchemaViolation, Unavailable,
                    Usage, extraction_model)

API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float = 45.0, max_output_tokens: int = 1500):
        self._key = api_key
        self.model = model
        self._timeout = timeout
        self._max_tokens = max_output_tokens

    def extract(self, req: ExtractRequest) -> ExtractResult:
        if not req.page_text:
            raise NotAvailable("text_required")
        model = extraction_model(req.doc_type, [f.name for f in req.fields])
        return self._run(ExtractResult, model, prompts.EXTRACT_SYSTEM,
                         prompts.text_user_message(prompts.extract_task(req), req.page_text))

    def classify(self, req: ClassifyRequest) -> ClassifyResult:
        if not req.page_text:
            raise NotAvailable("text_required")
        return self._run(ClassifyResult, ClassifyResponse, prompts.CLASSIFY_SYSTEM,
                         prompts.text_user_message(prompts.classify_task(req), req.page_text))

    def explain(self, req: ExplainRequest) -> ExplainResult:
        return self._run(ExplainResult, ExplainResponse, prompts.EXPLAIN_SYSTEM, prompts.explain_task(req))

    def _run(self, result_cls: type[ProviderResult], schema_model: type[BaseModel], system: str, user: str) -> Any:
        if not self._key:
            raise MissingKey()
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_completion_tokens": self._max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "pramaan_response", "strict": True, "schema": to_schema(schema_model, "groq")}},
        }
        started = time.monotonic()
        body = http.post_json(API_URL, {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"},
                              payload, self._timeout)
        latency = int((time.monotonic() - started) * 1000)
        try:
            choice = body["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise Unavailable("bad_shape") from None
        if choice.get("finish_reason") == "length":
            raise SchemaViolation("truncated")
        try:
            validated = schema_model.model_validate(json.loads(text))
        except (TypeError, ValueError, ValidationError):
            raise SchemaViolation() from None
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        return result_cls(available=True, response=validated, provider=self.name, model=self.model,
                          usage=Usage(_int(usage.get("prompt_tokens")), _int(usage.get("completion_tokens")), latency))


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
