"""The provider interface and the ordered fallback chain."""
from __future__ import annotations

from typing import Protocol

from .config import AIConfig
from .fixture import FaultInjector, FixtureProvider
from .gemini import GeminiProvider
from .groq import GroqProvider
from .none import NoneProvider
from .types import (ClassifyRequest, ClassifyResult, ExplainRequest, ExplainResult, ExtractRequest, ExtractResult)


class AIProvider(Protocol):
    name: str
    model: str

    def extract(self, req: ExtractRequest) -> ExtractResult: ...    # schema-constrained field proposals
    def classify(self, req: ClassifyRequest) -> ClassifyResult: ...  # document-type check
    def explain(self, req: ExplainRequest) -> ExplainResult: ...    # plain-language wording of a finding


def build_chain(cfg: AIConfig) -> list[AIProvider]:
    """primary model -> secondary model -> fallback provider. Empty when AI is off.

    ``fixture`` and ``AI_TEST_FAULT`` exist only under APP_ENV=test (``load_config`` refuses them elsewhere)."""
    chain = _chain(cfg)
    if cfg.test_fault:
        return [FaultInjector(p, cfg.test_fault) for p in chain]
    return chain


def _chain(cfg: AIConfig) -> list[AIProvider]:
    if not cfg.enabled:
        return []
    if cfg.provider == "fixture":
        return [FixtureProvider()]
    groq = GroqProvider(cfg.groq_key, cfg.fallback_model, cfg.timeout_seconds)
    if cfg.provider == "groq":
        return [groq]
    chain: list[AIProvider] = [GeminiProvider(cfg.gemini_key, cfg.model_primary, cfg.timeout_seconds)]
    if cfg.model_secondary and cfg.model_secondary != cfg.model_primary:
        chain.append(GeminiProvider(cfg.gemini_key, cfg.model_secondary, cfg.timeout_seconds))
    if cfg.fallback_provider == "groq":
        chain.append(groq)
    return chain


__all__ = ["AIProvider", "NoneProvider", "build_chain"]
