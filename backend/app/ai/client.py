"""Reliability around the providers: fallback chain, bounded retries, daily budget, response cache, kill switch.

    primary model -> (429/5xx/timeout) -> secondary model -> (429/5xx/timeout) -> fallback provider -> none

At most three provider requests are made per call. Persistent state (cache, counters, status) goes through the
connection the caller already holds, so it joins the caller's transaction. When the pipeline hands us a connection
inside its write transaction, the network round-trips run with that write lock *released* (``outside_write_lock``):
a slow provider must not stall every other writer. The accounting for a paid request is checkpointed straight away so
a later local failure cannot lose it. Logs carry task, provider, model, latency, token counts, cache flag and an error
*code* only.
"""
from __future__ import annotations

import hashlib
import logging
import random
import sqlite3
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, ContextManager, Iterator

from pydantic import BaseModel, ValidationError

from ..db import dumps, loads, now_iso
from .config import AIConfig, get_config
from .prompts import PROMPT_VERSION, SCHEMA_VERSION
from .provider import AIProvider, build_chain
from .types import (AIError, ClassifyRequest, ClassifyResponse, ClassifyResult, ExplainRequest, ExplainResponse,
                    ExplainResult, ExtractRequest, ExtractResult, MissingKey, NotAvailable, ProviderResult, Usage,
                    extraction_model)

log = logging.getLogger("pramaan.ai")
MAX_ATTEMPTS = 3
CACHE_TTL_DAYS = 30


@dataclass
class Outcome:
    """What a caller gets back. ``result`` is None when the AI step must be skipped; ``skipped`` says why."""
    result: ProviderResult | None = None
    skipped: str | None = None
    provider: str = "none"
    model: str = ""
    cache_hit: bool = False
    attempts: int = 0
    latency_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.result is not None


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@contextmanager
def outside_write_lock(conn: sqlite3.Connection) -> Iterator[None]:
    """Commit the open write transaction, let the caller do slow I/O, then take the write lock again.

    Used by pipeline steps that were handed a connection inside ``BEGIN IMMEDIATE``. Everything written before the
    block is committed (the pipeline re-reads it afterwards); the work after it starts a fresh transaction that the
    pipeline commits as usual.
    """
    if not conn.in_transaction:
        yield
        return
    conn.execute("COMMIT")
    try:
        yield
    finally:
        conn.execute("BEGIN IMMEDIATE")


# --------------------------------------------------------------------------- persistent state helpers
def get_state(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM ai_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO ai_state (key, value, updated_at) VALUES (?,?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                 (key, value, now_iso()))


def kill_switch_engaged(conn: sqlite3.Connection) -> bool:
    return get_state(conn, "kill_switch") == "1"


def usage_today(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute("SELECT * FROM ai_usage_daily WHERE day=?", (today(),)).fetchone()
    if row is None:
        return {"requests": 0, "pages": 0, "cache_hits": 0, "failures": 0, "input_tokens": 0, "output_tokens": 0,
                "latency_ms": 0}
    return {k: row[k] for k in ("requests", "pages", "cache_hits", "failures", "input_tokens", "output_tokens", "latency_ms")}


def _bump(conn: sqlite3.Connection, **inc: int) -> None:
    cols = ("requests", "pages", "cache_hits", "failures", "input_tokens", "output_tokens", "latency_ms")
    values = [int(inc.get(c, 0)) for c in cols]
    conn.execute(
        "INSERT INTO ai_usage_daily (day, requests, pages, cache_hits, failures, input_tokens, output_tokens, latency_ms)"
        " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET " +
        ", ".join(f"{c}={c}+excluded.{c}" for c in cols), (today(), *values))


def record_error(conn: sqlite3.Connection, code: str) -> None:
    set_state(conn, "last_error_code", code)
    set_state(conn, "last_error_at", now_iso())


# ------------------------------------------------------------------------------------------- client
class AIClient:
    def __init__(self, conn: sqlite3.Connection, cfg: AIConfig | None = None, *,
                 chain: list[AIProvider] | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, rng: Callable[[], float] = random.random,
                 unlock: Callable[[sqlite3.Connection], ContextManager[None]] | None = None):
        self.conn = conn
        self.cfg = cfg or get_config()
        self._chain = chain
        self._sleep, self._clock, self._rng = sleep, clock, rng
        self._unlock = unlock

    # -------------------------------------------------------------------------------- public tasks
    def extract(self, req: ExtractRequest, subject_sha: str, pages: int) -> Outcome:
        schema = extraction_model(req.doc_type, [f.name for f in req.fields])
        variant = f"{req.doc_type}:{','.join(sorted(f.name for f in req.fields))}:pages={pages}"
        return self._call("extract", req, schema, ExtractResult, subject_sha, pages, variant)

    def classify(self, req: ClassifyRequest, subject_sha: str, pages: int) -> Outcome:
        variant = f"types={','.join(sorted(req.labels))}:pages={pages}"
        return self._call("classify", req, ClassifyResponse, ClassifyResult, subject_sha, pages, variant)

    def explain(self, req: ExplainRequest, subject_sha: str) -> Outcome:
        return self._call("explain", req, ExplainResponse, ExplainResult, subject_sha, 0, f"lang={req.language}")

    # ------------------------------------------------------------------------------------ internals
    def _key(self, subject_sha: str, task: str, model: str, variant: str) -> str:
        return hashlib.sha256("|".join([subject_sha, task, model, SCHEMA_VERSION, PROMPT_VERSION, variant]).encode()).hexdigest()

    def _cached(self, key: str, schema: type[BaseModel], result_cls: type[ProviderResult]) -> ProviderResult | None:
        row = self.conn.execute("SELECT * FROM ai_cache WHERE cache_key=?", (key,)).fetchone()
        if row is None:
            return None
        try:  # a cached answer is re-validated exactly like a fresh one
            response = schema.model_validate(loads(row["response_json"]))
        except (ValidationError, ValueError):
            self.conn.execute("DELETE FROM ai_cache WHERE cache_key=?", (key,))
            return None
        return result_cls(available=True, response=response, provider="cache", model=row["model"],
                          usage=Usage(row["input_tokens"], row["output_tokens"], 0))

    def _network(self) -> ContextManager[None]:
        return self._unlock(self.conn) if self._unlock else nullcontext()

    def _checkpoint(self) -> None:
        """Make the accounting of what was just spent durable, whatever the caller does next."""
        if self._unlock and self.conn.in_transaction:
            self.conn.execute("COMMIT")
            self.conn.execute("BEGIN IMMEDIATE")

    def _call(self, task: str, request: Any, schema: type[BaseModel], result_cls: type[ProviderResult],
              subject_sha: str, pages: int, variant: str) -> Outcome:
        cfg = self.cfg
        if not cfg.enabled:
            return Outcome(skipped="disabled")
        if kill_switch_engaged(self.conn):
            return Outcome(skipped="kill_switch")
        chain = self._chain if self._chain is not None else build_chain(cfg)

        for provider in chain:  # re-runs cost nothing
            hit = self._cached(self._key(subject_sha, task, provider.model, variant), schema, result_cls)
            if hit is not None:
                _bump(self.conn, cache_hits=1)
                log.info("ai_call task=%s provider=cache model=%s cache=hit code=ok", task, provider.model)
                return Outcome(hit, provider=provider.name, model=hit.model, cache_hit=True)

        used = usage_today(self.conn)
        if used["requests"] >= cfg.daily_request_budget:
            record_error(self.conn, "budget_exhausted")
            return Outcome(skipped="budget_exhausted")
        if pages and used["pages"] + pages > cfg.daily_page_budget:
            record_error(self.conn, "page_budget_exhausted")
            return Outcome(skipped="page_budget_exhausted")
        cutoff = (datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)).isoformat(timespec="seconds")
        self.conn.execute("DELETE FROM ai_cache WHERE created_at < ?", (cutoff,))

        # ------------------------------------------------ the provider requests (no database access in here)
        started = self._clock()
        attempts, last_code = 0, "unavailable"
        failures: list[tuple[str, str]] = []     # (provider name, error code) for every request that went out
        winner: tuple[int, AIProvider, ProviderResult] | None = None
        with self._network():
            for index, provider in enumerate(chain):
                if attempts >= MAX_ATTEMPTS:
                    break
                remaining = cfg.call_deadline_seconds - (self._clock() - started)
                if remaining <= 0:
                    last_code = "deadline"
                    break
                if attempts:  # exponential backoff with jitter between real attempts
                    self._sleep(min(4.0, 0.5 * 2 ** (attempts - 1)) * (0.5 + self._rng()))
                    remaining = cfg.call_deadline_seconds - (self._clock() - started)
                    if remaining <= 0:
                        last_code = "deadline"
                        break
                if hasattr(provider, "deadline_timeout"):  # one slow request cannot outlast the whole call's deadline
                    provider.deadline_timeout = max(1.0, remaining)
                try:
                    result = getattr(provider, task)(request)
                    if not result.available:
                        raise NotAvailable()
                except (MissingKey, NotAvailable) as exc:  # nothing was sent, so it is not an attempt
                    last_code = exc.code
                    continue
                except AIError as exc:
                    attempts += 1
                    last_code = exc.code
                    failures.append((provider.name, exc.code))
                    log.warning("ai_call task=%s provider=%s model=%s cache=miss code=%s", task, provider.name,
                                provider.model, exc.code)
                    continue
                attempts += 1
                winner = (index, provider, result)
                break

        # ------------------------------------------------------------------------- accounting (write lock held again)
        for _, code in failures:
            _bump(self.conn, requests=1, pages=pages, failures=1)
            record_error(self.conn, code)
        if winner is None:
            if attempts:
                set_state(self.conn, "fallback_active", "1")
            else:
                record_error(self.conn, last_code)
            self._checkpoint()
            return Outcome(skipped=last_code, attempts=attempts)
        index, provider, result = winner
        usage = result.usage
        _bump(self.conn, requests=1, pages=pages, input_tokens=usage.input_tokens or 0,
              output_tokens=usage.output_tokens or 0, latency_ms=usage.latency_ms)
        self.conn.execute(
            "INSERT OR REPLACE INTO ai_cache (cache_key, subject_sha256, task, model, schema_version, prompt_version,"
            " variant, response_json, input_tokens, output_tokens, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (self._key(subject_sha, task, provider.model, variant), subject_sha, task, provider.model, SCHEMA_VERSION,
             PROMPT_VERSION, variant, dumps(result.payload()), usage.input_tokens, usage.output_tokens, now_iso()))
        set_state(self.conn, "fallback_active", "1" if index > 0 else "0")
        self._checkpoint()
        log.info("ai_call task=%s provider=%s model=%s latency_ms=%d in_tokens=%s out_tokens=%s cache=miss code=ok",
                 task, provider.name, provider.model, usage.latency_ms, usage.input_tokens, usage.output_tokens)
        return Outcome(result, provider=provider.name, model=provider.model, attempts=attempts, latency_ms=usage.latency_ms)


# ------------------------------------------------------------------------------------------- status
def build_status(conn: sqlite3.Connection, cfg: AIConfig | None = None) -> dict[str, Any]:
    cfg = cfg or get_config()
    u = usage_today(conn)
    models = {"primary": cfg.model_primary, "secondary": cfg.model_secondary,
              "fallback": f"{cfg.fallback_provider}:{cfg.fallback_model}" if cfg.fallback_provider != "none" else "none"}
    if cfg.provider == "groq":
        models = {"primary": f"groq:{cfg.fallback_model}", "secondary": "none", "fallback": "none"}
    if cfg.provider == "none":
        models = {"primary": "none", "secondary": "none", "fallback": "none"}
    return {
        "provider": cfg.provider, "models": models,
        "mode": "off" if (not cfg.enabled or kill_switch_engaged(conn)) else cfg.data_policy,
        "kill_switch": kill_switch_engaged(conn),
        "requests_today": u["requests"], "budget": {"requests": cfg.daily_request_budget, "pages": cfg.daily_page_budget},
        "pages_today": u["pages"], "last_error_code": get_state(conn, "last_error_code"),
        "last_error_at": get_state(conn, "last_error_at"), "fallback_active": get_state(conn, "fallback_active") == "1",
        "cache_hits_today": u["cache_hits"],
    }
