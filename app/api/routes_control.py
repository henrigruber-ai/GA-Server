"""
File: app/api/routes_control.py
Version: 0.3.0
Date: 2026-08-06
Purpose: Exposes authenticated Tasmota snapshots, power commands, and control events.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from app.api.schemas import PowerInput
from app.auth.security import COOKIE_NAME
from app.core.time import utc_now
from app.db.models import Session as UserSession
from app.db.models import User
from app.runtime import Runtime
from app.services.device_control import DeviceControlError

router = APIRouter(prefix="/api/admin/control", tags=["control"])


def _authorize(request: Request, *, csrf: bool = False) -> tuple[User, UserSession]:
    runtime = request.app.state.runtime
    user, session = runtime.auth.authenticate(request)
    if csrf:
        runtime.auth.require_csrf(request, session)
    return user, session


def _snapshot(runtime: Runtime) -> dict[str, object]:
    devices = runtime.control.snapshot_devices()
    latest = runtime.live_store.latest()
    for device in devices:
        device_id = device.get("id")
        measurement = latest.get(device_id) if isinstance(device_id, str) else None
        device["live"] = measurement.public_dict() if measurement else None
    return {"server_time": utc_now().isoformat(), "devices": devices}


@router.get("/devices")
def devices(request: Request) -> dict[str, object]:
    _authorize(request)
    return _snapshot(request.app.state.runtime)


@router.post("/devices/{device_id}/power", status_code=202)
def power(device_id: str, payload: PowerInput, request: Request) -> dict[str, object]:
    user, _session = _authorize(request, csrf=True)
    try:
        state = request.app.state.runtime.control.request_power(
            device_id,
            payload.state == "on",
            user,
        )
    except DeviceControlError as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={"code": error.code, "message": error.message},
        ) from error
    return {"status": "pending", "device_id": device_id, "control": state}


@router.websocket("-stream")
async def control_stream(websocket: WebSocket) -> None:
    runtime = websocket.app.state.runtime
    raw_token = websocket.cookies.get(COOKIE_NAME)
    if not raw_token:
        await websocket.close(code=4401, reason="Anmeldung erforderlich")
        return
    try:
        runtime.auth.authenticate_token(raw_token)
    except HTTPException:
        await websocket.close(code=4401, reason="Sitzung ungültig")
        return
    await runtime.control_websockets.connect(websocket)
    try:
        await websocket.send_json({"type": "snapshot", "data": _snapshot(runtime)})
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except TimeoutError:
                await websocket.send_json({"type": "ping", "server_time": utc_now().isoformat()})
    except WebSocketDisconnect:
        pass
    finally:
        await runtime.control_websockets.disconnect(websocket)
