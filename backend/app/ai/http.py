"""The only place that touches the network for AI. Tests replace ``post_json``; CI never calls a live API.

Exceptions carry a short code only: provider bodies can echo prompts or document text, so they are never kept.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import requests

from .types import AuthError, BadRequest, RateLimited, Unavailable

ALLOWED_HOSTS = frozenset({"generativelanguage.googleapis.com", "api.groq.com"})


def post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise BadRequest("host_not_allowed")
    try:
        # No redirects: a redirect would carry the API-key header to another host.
        response = requests.post(url, headers=headers, json=payload, timeout=timeout, allow_redirects=False)
    except requests.Timeout:
        raise Unavailable("timeout") from None
    except requests.RequestException:
        raise Unavailable("network") from None
    status = response.status_code
    if status == 429:
        raise RateLimited()
    if status >= 500:
        raise Unavailable(f"http_{status}")
    if status in (401, 403):
        raise AuthError()
    if status >= 300:
        raise BadRequest(f"http_{status}")
    try:
        body = response.json()
    except ValueError:
        raise Unavailable("bad_json") from None
    if not isinstance(body, dict):
        raise Unavailable("bad_json")
    return body
