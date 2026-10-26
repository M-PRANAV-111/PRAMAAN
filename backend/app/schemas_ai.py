"""API shapes for the AI layer and routing. Kept apart from ``schemas.py`` so the shared contract stays untouched;
``scripts/gen_contract.py`` includes this module."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from .schemas import Model

RoutingOutcome = Literal["READY_FOR_SCRUTINY", "CORRECTIONS_REQUIRED", "OFFICER_REVIEW_REQUIRED"]
AiProviderName = Literal["none", "gemini", "groq", "fixture"]  # fixture: APP_ENV=test only
AiMode = Literal["off", "synthetic_only", "allow_real"]


class AiBudgetOut(Model):
    requests: int
    pages: int


class AiStatusOut(Model):
    provider: AiProviderName
    models: dict[str, str]
    mode: AiMode
    kill_switch: bool
    requests_today: int
    budget: AiBudgetOut
    pages_today: int
    last_error_code: str | None = None
    last_error_at: str | None = None
    fallback_active: bool
    cache_hits_today: int
    simulated: bool = False  # true for the recorded test fixture; label it wherever status is shown


class KillSwitchRequest(Model):
    engaged: bool
    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


class RoutingReasonOut(Model):
    code: str
    text: str
    finding_id: str | None = None
    document_id: str | None = None


class AutomatedActionOut(Model):
    type: str
    summary: str
    notified: int | None = None


class RoutingOut(Model):
    outcome: RoutingOutcome
    reasons: list[RoutingReasonOut]
    automated_actions: list[AutomatedActionOut]
    run_id: str | None = None
    computed_at: str
    ai_used: bool
    policy_version: str


class JobNoteOut(Model):
    id: str
    level: Literal["INFO"]
    text: str
    created_at: str


class AiSuggestionReview(Model):
    """An officer's decision on an AI suggestion that could not be grounded on the page."""
    field: str = Field(min_length=1, max_length=60)
    decision: Literal["CONFIRM", "DISMISS"]
    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value
