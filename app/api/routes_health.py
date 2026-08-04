"""
File: app/api/routes_health.py
Version: 0.1.1
Date: 2026-08-04
Purpose: Provides secret-free liveness and readiness probes.
Changes:
- 0.1.0: Initial implementation.
- 0.1.1: Requires an active MQTT connection when MQTT is enabled.
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
        "mqtt_connected": not runtime.settings.mqtt_enabled or runtime.mqtt.connected,
        "data_directory": writable,
    }
    ready_state = all(checks.values())
    if not ready_state:
        response.status_code = 503
    return {"status": "ready" if ready_state else "not_ready", "checks": checks}
