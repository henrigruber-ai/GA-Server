"""
File: app/main.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Creates the FastAPI application, lifecycle, security headers, and web entry point.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import __version__
from app.api.routes_admin import router as admin_router
from app.api.routes_auth import router as auth_router
from app.api.routes_control import router as control_router
from app.api.routes_health import router as health_router
from app.api.routes_public import router as public_router
from app.config import Settings
from app.config import settings as default_settings
from app.runtime import Runtime

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path.cwd() if (Path.cwd() / "VERSION").is_file() else PACKAGE_ROOT.parent
WEB_ROOT = PACKAGE_ROOT / "web"


def create_app(app_settings: Settings | None = None) -> FastAPI:
    active_settings = app_settings or default_settings
    logging.basicConfig(
        level=getattr(logging, active_settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    runtime = Runtime.build(active_settings, PROJECT_ROOT)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.runtime = runtime
        application.state.project_root = PROJECT_ROOT
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()

    application = FastAPI(
        title="GA-Server",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs" if active_settings.environment != "production" else None,
        redoc_url=None,
    )
    application.state.runtime = runtime
    application.state.project_root = PROJECT_ROOT
    application.mount("/static", StaticFiles(directory=WEB_ROOT / "static"), name="static")
    application.include_router(public_router)
    application.include_router(auth_router)
    application.include_router(admin_router)
    application.include_router(control_router)
    application.include_router(health_router)

    templates = Environment(
        loader=FileSystemLoader(WEB_ROOT / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )

    @application.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self' ws: wss:; "
            "img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if active_settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request) -> HTMLResponse:
        template = templates.get_template("index.html")
        return HTMLResponse(
            template.render(
                request=request,
                version=__version__,
                timezone=active_settings.timezone,
                public_site=active_settings.public_base_url,
                mqtt_endpoint=(
                    f"{active_settings.mqtt_public_host}:{active_settings.mqtt_public_port}"
                ),
            )
        )

    return application


app = create_app()
