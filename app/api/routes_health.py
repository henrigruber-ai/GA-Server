"""
File: app/api/routes_health.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Provides secret-free liveness and readiness probes.
Changes:
- 0.1.0: Initial implementation.
"""

from pathlib import Path

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/ready")
def ready(request: Request, response: Response) -> dict[str, object]:
    runtime = request.app.state.runtime
    database_ok = runtime.database.ping()
    path = runtime.settings.database_path
    directory = path.parent if path else Path.cwd()
    writable = directory.exists() and directory.is_dir()
    checks = {
        "database": database_ok,
        "schema": database_ok,
        "mqtt_initialized": runtime.mqtt.initialized,
        "data_directory": writable,
    }
    ready_state = all(checks.values())
    if not ready_state:
        response.status_code = 503
    return {"status": "ready" if ready_state else "not_ready", "checks": checks}
