"""Test-only pieces of the provider chain. ``load_config`` refuses both unless ``APP_ENV=test``.

``FixtureProvider`` replays hand-authored answers from ``fixtures/<task>_<doc_type>.json`` so a real server, started
by the browser suite, can exercise the AI path without a key or the network. It never reads the document to build an
answer: the answer is looked up by document type and then goes through the same validation, grounding and policy as a
live answer. A value it proposes that is not printed on the page becomes a suggestion, never a claim.

``FaultInjector`` wraps any provider and fails each request the way the network layer would (``AI_TEST_FAULT``):
``rate_limit`` -> HTTP 429, ``timeout`` -> a request timeout, ``invalid_json`` -> an answer that breaks the schema.
The client's real retry, fallback, accounting and job-note code then runs unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .types import (AIError, ClassifyRequest, ClassifyResponse, ClassifyResult, ExplainRequest, ExplainResult,
                    ExtractRequest, ExtractResult, NotAvailable, RateLimited, SchemaViolation, Unavailable, Usage,
                    extraction_model)

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_MODEL = "recorded-test-fixture"


class FixtureProvider:
    name = "fixture"
    model = FIXTURE_MODEL

    def extract(self, req: ExtractRequest) -> ExtractResult:
        recorded = _load(f"extract_{req.doc_type}")
        names = [f.name for f in req.fields]
        empty = {"value": None, "page": None, "quote": None}
        answer = {name: recorded.get(name, empty) for name in names}  # exactly the requested fields
        return ExtractResult(available=True, response=_validate(extraction_model(req.doc_type, names), answer),
                             provider=self.name, model=self.model, usage=Usage(None, None, 0))

    def classify(self, req: ClassifyRequest) -> ClassifyResult:
        recorded = _load(f"classify_{req.expected_type}")
        return ClassifyResult(available=True, response=_validate(ClassifyResponse, recorded), provider=self.name,
                              model=self.model, usage=Usage(None, None, 0))

    def explain(self, req: ExplainRequest) -> ExplainResult:
        # Wording depends on each finding's proof, so nothing can be recorded once for all; the template stays.
        raise NotAvailable("no_fixture")


class FaultInjector:
    """Delegates to ``inner`` after failing the request; nothing reaches the network or the inner provider."""

    def __init__(self, inner: Any, fault: str):
        self._inner = inner
        self._fault = fault
        self.name = inner.name
        self.model = inner.model

    def _fail(self) -> None:
        if self._fault == "rate_limit":
            raise RateLimited()
        if self._fault == "timeout":
            raise Unavailable("timeout")
        if self._fault == "invalid_json":
            raise SchemaViolation()
        raise AIError("unknown_fault")

    def extract(self, req: ExtractRequest) -> ExtractResult:
        self._fail()
        return self._inner.extract(req)

    def classify(self, req: ClassifyRequest) -> ClassifyResult:
        self._fail()
        return self._inner.classify(req)

    def explain(self, req: ExplainRequest) -> ExplainResult:
        self._fail()
        return self._inner.explain(req)


def _load(name: str) -> dict[str, Any]:
    path = FIXTURES / f"{name}.json"
    if not path.is_file():
        raise NotAvailable("no_fixture")  # nothing was sent, so the client does not count an attempt
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SchemaViolation()
    return {k: v for k, v in data.items() if not k.startswith("_")}  # "_comment" keys document the recording


def _validate(model: type[BaseModel], data: dict[str, Any]) -> BaseModel:
    try:
        return model.model_validate(data)
    except ValidationError:
        raise SchemaViolation() from None
