"""ASGI application factory."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import api
from .config import get_settings
from .db import migrate, transaction
from .pipeline.orchestrator import worker
from .rulepacks import install_from_files
from .routes import applications, auth, documents, oversight, system  # noqa: F401 — registers routes

log = logging.getLogger("pramaan")

CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "font-src 'self' data:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        rid = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        response: Response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Content-Security-Policy", CSP)
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if get_settings().env == "production":
            h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.url.path.startswith("/api/"):
            h.setdefault("Cache-Control", "no-store")
        h["X-Request-ID"] = rid
        # Structured access log: method, route, status, timing — no bodies, no query values, no cookies.
        log.info("request id=%s method=%s path=%s status=%s ms=%.1f", rid, request.method, request.url.path,
                 response.status_code, (time.perf_counter() - start) * 1000)
        return response


def _spa_routes(dist: Path) -> list:
    index = dist / "index.html"

    async def spa(request: Request) -> Response:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": {"code": "not_found", "message": "Unknown API route", "details": None}}, 404)
        if request.url.path in ("/sw.js", "/manifest.webmanifest", "/apple-touch-icon.png"):
            f = dist / "assets" / request.url.path.lstrip("/")
            if f.is_file():
                media = ("application/javascript" if f.suffix == ".js"
                         else "application/manifest+json" if f.suffix == ".webmanifest"
                         else "image/png")
                return FileResponse(f, media_type=media, headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return [Mount("/assets", app=StaticFiles(directory=dist / "assets"), name="assets"),
            Route("/{path:path}", spa, methods=["GET"])]


def bootstrap() -> None:
    migrate()
    with transaction() as c:
        install_from_files(c)


def create_app() -> Starlette:
    s = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    @asynccontextmanager
    async def lifespan(app: Starlette):
        bootstrap()
        worker.start()
        yield

    routes = api.starlette_routes()

    async def api_not_found(request: Request) -> Response:
        return JSONResponse({"error": {"code": "not_found", "message": "Unknown API route", "details": None}}, 404)

    routes.append(Route("/api/{rest:path}", api_not_found, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]))
    if s.front_dist and (s.front_dist / "index.html").exists():
        routes.extend(_spa_routes(s.front_dist))
    middleware = [Middleware(SecurityHeaders)]
    if s.cors_origins:
        middleware.append(Middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                                     allow_methods=["GET", "POST"], allow_headers=["content-type", "x-requested-with"]))
    return Starlette(routes=routes, middleware=middleware, lifespan=lifespan)


app = create_app()
