"""Explicit feature and system-extension registries; unavailable features stay false."""
from collections.abc import Callable
from typing import Any

_features: dict[str, bool | Callable[[], bool]] = {
    name: False for name in ("registration", "password_reset", "notifications", "timeline", "reports", "clarifications")
}
_system: dict[str, Callable[[], Any]] = {}


def register(name: str, available: bool | Callable[[], bool] = True) -> None:
    _features[name] = available


def snapshot() -> dict[str, bool]:
    return {name: bool(value() if callable(value) else value) for name, value in _features.items()}


def register_system_extra(name: str, fn: Callable[[], Any]) -> None:
    _system[name] = fn


def system_extras() -> dict[str, Any]:
    return {name: fn() for name, fn in _system.items()}
