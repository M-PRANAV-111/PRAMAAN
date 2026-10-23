"""A small typed routing layer over Starlette.

Each handler is registered with its request/response Pydantic models and allowed roles. The same
registry drives request validation, authorization, response serialization and the generated
OpenAPI contract, so the contract cannot drift from the code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .security import Principal, decode_token

log = logging.getLogger("pramaan.api")
SESSION_COOKIE = "pramaan_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "pramaan"
MAX_JSON_BYTES = 256 * 1024


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def error_response(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "details": details}}, status_code=status)


@dataclass
class UploadedFile:
    filename: str
    content_type: str
    data: bytes


@dataclass
class Ctx:
    request: Request
    principal: Principal | None
    path: dict[str, str]
    query: dict[str, str]
    body: Any = None
    form: dict[str, str] = field(default_factory=dict)
    file: UploadedFile | None = None
    client_ip: str = "unknown"

    @property
    def user(self) -> Principal:
        assert self.principal is not None
        return self.principal


@dataclass
class RouteSpec:
    method: str
    path: str
    handler: Callable[[Ctx], Any]
    summary: str
    tag: str
    roles: tuple[str, ...] | None
    public: bool
    body: type[BaseModel] | None
    response: Any
    status: int
    multipart: bool
    raw: bool
    query: dict[str, str]


REGISTRY: list[RouteSpec] = []


def route(method: str, path: str, *, summary: str, tag: str, response: Any = None, body: type[BaseModel] | None = None,
          roles: tuple[str, ...] | None = None, public: bool = False, status: int = 200, multipart: bool = False,
          raw: bool = False, query: dict[str, str] | None = None) -> Callable[[Callable[[Ctx], Any]], Callable[[Ctx], Any]]:
    def deco(fn: Callable[[Ctx], Any]) -> Callable[[Ctx], Any]:
        REGISTRY.append(RouteSpec(method, path, fn, summary, tag, roles, public, body, response, status, multipart, raw,
                                  query or {}))
        return fn
    return deco


def principal_from_request(request: Request) -> tuple[Principal | None, bool]:
    """Returns (principal, via_cookie)."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return decode_token(auth[7:].strip()), False
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        return decode_token(token), True
    return None, False


async def _read_upload(request: Request, max_bytes: int) -> tuple[dict[str, str], UploadedFile | None]:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > max_bytes + 64 * 1024:
        raise ApiError(413, "payload_too_large", f"Upload exceeds {max_bytes // (1024 * 1024)} MB")
    form = await request.form(max_files=1, max_fields=8)
    fields: dict[str, str] = {}
    upload: UploadedFile | None = None
    try:
        for key, value in form.multi_items():
            if hasattr(value, "read"):
                data = await value.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ApiError(413, "payload_too_large", f"Upload exceeds {max_bytes // (1024 * 1024)} MB")
                upload = UploadedFile(value.filename or "upload", value.content_type or "", data)
            else:
                fields[key] = str(value)[:500]
    finally:
        await form.close()
    return fields, upload


def _serialize(spec: RouteSpec, result: Any) -> Response:
    if isinstance(result, Response):
        return result
    model = spec.response
    if model is None:
        return JSONResponse(result, status_code=spec.status)
    origin = getattr(model, "__origin__", None)
    if origin is list:
        inner = model.__args__[0]
        payload = [inner.model_validate(r).model_dump(mode="json") for r in result]
    else:
        payload = model.model_validate(result).model_dump(mode="json")
    return JSONResponse(payload, status_code=spec.status)


def _make_endpoint(spec: RouteSpec) -> Callable[[Request], Any]:
    async def endpoint(request: Request) -> Response:
        from .config import get_settings
        try:
            principal, via_cookie = principal_from_request(request)
            if not spec.public:
                if principal is None:
                    raise ApiError(401, "unauthenticated", "Sign in to continue")
                if spec.roles and principal.role not in spec.roles:
                    raise ApiError(403, "forbidden", "Your role cannot perform this action")
            if spec.method != "GET" and via_cookie and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
                raise ApiError(403, "csrf", "Missing anti-forgery header")
            ctx = Ctx(request=request, principal=principal, path=dict(request.path_params),
                      query={k: v for k, v in request.query_params.items()},
                      client_ip=request.client.host if request.client else "unknown")
            if spec.body is not None:
                raw = await request.body()
                if len(raw) > MAX_JSON_BYTES:
                    raise ApiError(413, "payload_too_large", "Request body too large")
                try:
                    ctx.body = spec.body.model_validate_json(raw or b"{}")
                except ValidationError as exc:
                    details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
                    raise ApiError(422, "validation_error", "Request did not match the expected shape", details) from None
            if spec.multipart:
                ctx.form, ctx.file = await _read_upload(request, get_settings().max_upload_bytes)
            result = await run_in_threadpool(spec.handler, ctx)
            return _serialize(spec, result)
        except ApiError as e:
            return error_response(e.status, e.code, e.message, e.details)
        except Exception:  # never leak internals
            log.exception("unhandled error on %s %s", spec.method, spec.path)
            return error_response(500, "internal_error", "Something went wrong. The incident has been logged.")
    endpoint.__name__ = spec.handler.__name__
    return endpoint


def starlette_routes() -> list[Route]:
    return [Route(s.path, _make_endpoint(s), methods=[s.method]) for s in REGISTRY]
