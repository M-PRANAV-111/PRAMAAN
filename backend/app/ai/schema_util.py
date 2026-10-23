"""Turn Pydantic models into the JSON-Schema subset structured-output endpoints accept.

Gemini ignores ``minLength``/``maxLength``/``minProperties``/``maxProperties``/``uniqueItems`` and very large or
deeply nested schemas return 400, so schemas are inlined (no ``$ref``), nullable unions become type arrays, and
every ignored keyword is removed. Those limits are enforced again by Pydantic when the response arrives.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Removed for every provider: not enforced (or not accepted) by constrained decoding.
UNSUPPORTED = frozenset({
    "title", "default", "minLength", "maxLength", "minProperties", "maxProperties", "uniqueItems", "contains",
    "minContains", "maxContains", "pattern", "examples", "$defs", "$schema", "$id", "exclusiveMinimum",
    "exclusiveMaximum", "multipleOf",
})
# Additionally removed for Groq strict mode.
GROQ_EXTRA = frozenset({"minimum", "maximum", "minItems", "maxItems"})


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_inline(n, defs) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        target = defs[node["$ref"].rsplit("/", 1)[-1]]
        return _inline({**target, **{k: v for k, v in node.items() if k != "$ref"}}, defs)
    return {k: _inline(v, defs) for k, v in node.items()}


def _clean(node: Any, drop: frozenset[str]) -> Any:
    if isinstance(node, list):
        return [_clean(n, drop) for n in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties":  # property *names* are data: a field called "title" must survive
            out[key] = {name: _clean(sub, drop) for name, sub in value.items()}
        elif key not in drop:
            out[key] = _clean(value, drop)
    any_of = out.get("anyOf")
    if isinstance(any_of, list):
        kinds = [a for a in any_of if a != {"type": "null"}]
        if len(kinds) == 1 and len(any_of) == 2 and "type" in kinds[0] and isinstance(kinds[0]["type"], str):
            merged = {**kinds[0], "type": [kinds[0]["type"], "null"]}
            out.pop("anyOf")
            out.update(merged)
    if "const" in out:
        out["enum"] = [out.pop("const")]
    if out.get("type") == "object":
        out["additionalProperties"] = False
        out["required"] = sorted(out.get("properties", {}))
    return out


def to_schema(model: type[BaseModel], provider: str = "gemini") -> dict[str, Any]:
    raw = model.model_json_schema()
    defs = raw.get("$defs", {})
    inlined = _inline({k: v for k, v in raw.items() if k != "$defs"}, defs)
    drop = UNSUPPORTED | (GROQ_EXTRA if provider == "groq" else frozenset())
    return _clean(inlined, drop)


def depth(node: Any) -> int:
    if isinstance(node, dict):
        return 1 + max((depth(v) for v in node.values()), default=0)
    if isinstance(node, list):
        return max((depth(v) for v in node), default=0)
    return 0


def keywords(node: Any) -> set[str]:
    """Every key used anywhere in a schema (for tests that assert nothing unsupported leaked through)."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key != "properties":
                found.add(key)
                found |= keywords(value)
            else:
                for sub in value.values():
                    found |= keywords(sub)
    elif isinstance(node, list):
        for item in node:
            found |= keywords(item)
    return found
