"""AI configuration, read from the environment on every call (never cached), so a change takes effect immediately.

Keys are held in fields excluded from ``repr`` and are never logged. ``AI_PROVIDER=none`` (the default) disables
every AI code path.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal, Mapping

Provider = Literal["none", "gemini", "groq"]
DataPolicy = Literal["synthetic_only", "allow_real"]


class AIConfigError(ValueError):
    """Raised at startup for an unsafe or malformed AI configuration."""


@dataclass(frozen=True)
class AIConfig:
    provider: Provider = "none"
    model_primary: str = "gemini-3.8-flash"
    model_secondary: str = "gemini-3.5-flash-lite"
    fallback_provider: Literal["none", "groq"] = "groq"
    fallback_model: str = "openai/gpt-oss-120b"
    gemini_key: str = field(default="", repr=False)
    groq_key: str = field(default="", repr=False)
    timeout_seconds: float = 45.0
    call_deadline_seconds: float = 90.0
    daily_request_budget: int = 200
    daily_page_budget: int = 1000
    trigger_confidence: float = 0.80
    data_policy: DataPolicy = "synthetic_only"
    paid_tier_confirmed: bool = False
    routing_min_confidence: float = 0.85
    max_pages: int = 8

    @property
    def enabled(self) -> bool:
        return self.provider != "none"

    @property
    def mode(self) -> str:
        return "off" if not self.enabled else self.data_policy


def _bool(raw: str | None, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _num(env: Mapping[str, str], name: str, default: float, cast, lo: float, hi: float):
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError:
        raise AIConfigError(f"{name} must be a number") from None
    if not lo <= value <= hi:
        raise AIConfigError(f"{name} must be between {lo} and {hi}")
    return value


def load_config(env: Mapping[str, str] | None = None) -> AIConfig:
    """Parse and validate. Raises ``AIConfigError`` for anything unsafe."""
    env = os.environ if env is None else env
    provider = (env.get("AI_PROVIDER") or "none").strip().lower()
    if provider not in ("none", "gemini", "groq"):
        raise AIConfigError("AI_PROVIDER must be gemini, groq or none")
    fallback = (env.get("AI_FALLBACK_PROVIDER") or "groq").strip().lower()
    if fallback not in ("none", "groq"):
        raise AIConfigError("AI_FALLBACK_PROVIDER must be groq or none")
    policy = (env.get("AI_DATA_POLICY") or "synthetic_only").strip().lower()
    if policy not in ("synthetic_only", "allow_real"):
        raise AIConfigError("AI_DATA_POLICY must be synthetic_only or allow_real")
    paid = _bool(env.get("AI_PAID_TIER_CONFIRMED"), False)
    if policy == "allow_real" and not paid:
        # Free-tier Gemini inputs may be used to improve Google products; real documents need the paid tier.
        raise AIConfigError("AI_DATA_POLICY=allow_real requires AI_PAID_TIER_CONFIRMED=true")
    return AIConfig(
        provider=provider,  # type: ignore[arg-type]
        model_primary=(env.get("AI_MODEL_PRIMARY") or "gemini-3.8-flash").strip(),
        model_secondary=(env.get("AI_MODEL_SECONDARY") or "gemini-3.5-flash-lite").strip(),
        fallback_provider=fallback,  # type: ignore[arg-type]
        fallback_model=(env.get("AI_FALLBACK_MODEL") or "openai/gpt-oss-120b").strip(),
        gemini_key=(env.get("GEMINI_API_KEY") or "").strip(),
        groq_key=(env.get("GROQ_API_KEY") or "").strip(),
        timeout_seconds=_num(env, "AI_TIMEOUT_SECONDS", 45.0, float, 1, 600),
        call_deadline_seconds=_num(env, "AI_CALL_DEADLINE_SECONDS", 90.0, float, 1, 900),
        daily_request_budget=_num(env, "AI_DAILY_REQUEST_BUDGET", 200, int, 0, 1_000_000),
        daily_page_budget=_num(env, "AI_DAILY_PAGE_BUDGET", 1000, int, 0, 10_000_000),
        trigger_confidence=_num(env, "AI_TRIGGER_CONFIDENCE", 0.80, float, 0, 1),
        data_policy=policy,  # type: ignore[arg-type]
        paid_tier_confirmed=paid,
        routing_min_confidence=_num(env, "ROUTING_MIN_CONFIDENCE", 0.85, float, 0, 1),
        max_pages=_num(env, "AI_MAX_PAGES", 8, int, 1, 40),
    )


def get_config() -> AIConfig:
    """Fail closed: a malformed configuration disables AI instead of breaking a running pipeline."""
    try:
        return load_config()
    except AIConfigError:
        return AIConfig(provider="none")


def validate_startup() -> AIConfig:
    """Called once when the application is imported; an unsafe configuration stops the process."""
    return load_config()
