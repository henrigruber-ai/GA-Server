"""
File: app/api/routes_admin.py
Version: 0.3.1
Date: 2026-08-07
Purpose: Implements the authenticated and audited administration API.
Changes:
- 0.1.0: Initial implementation.
- 0.3.1: Stores device MQTT passwords only as Argon2 hashes and keeps existing hashes on blank edits.
"""

from __future__ import annotations

import colorsys
import json

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import __version__
from app.api.helpers import admin_device, iso
from app.api.schemas import DeleteDeviceInput, DeviceInput, DeviceUpdate, UserInput, UserUpdate
from app.auth.security import hash_mqtt_password, hash_password
from app.core.time import utc_now
from app.db.models import AuditLog, Device, User
from app.db.models import Session as UserSession

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _authorize(request: Request, *, csrf: bool = False) -> tuple[User, UserSession]:
    runtime = request.app.state.runtime
    user, session = runtime.auth.authenticate(request)
    if csrf:
        runtime.auth.require_csrf(request, session)
    return user, session


def _audit(
    request: Request,
    user_id: str,
    action: str,
    target_type: str,
    target_id: str,
    details: str = "",
) -> None:
    with request.app.state.runtime.database.sessions.begin() as session:
        session.add(
            AuditLog(
                user_id=user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                details=details[:2000],
            )
        )


@router.get("/devices")
def list_devices(request: Request) -> list[dict[str, object]]:
    _authorize(request)
    runtime = request.app.state.runtime
    with runtime.database.sessions() as session:
        rows = session.scalars(
            select(Device)
            .order_by(Device.removed_at.is_not(None), Device.sort_order, Device.name)
            .limit(500)
        ).all()
        return [admin_device(row, runtime.settings, runtime.live_store) for row in rows]


@router.post("/devices", status_code=201)
def create_device(payload: DeviceInput, request: Request) -> dict[str, object]:
    user, _ = _authorize(request, csrf=True)
    runtime = request.app.state.runtime
    color = payload.color or _generated_color(payload.technical_device_id)
    values = payload.model_dump(exclude={"color", "mqtt_password"})
    device = Device(
        **values,
        color=color,
        mqtt_password_hash=(
            hash_mqtt_password(payload.mqtt_password) if payload.mqtt_password else None
        ),
    )
    try:
        with runtime.database.sessions.begin() as session:
            session.add(device)
    except IntegrityError as error:
        raise HTTPException(
            status_code=409, detail="Geräte-ID, Topic oder Client-ID existiert bereits."
        ) from error
    _audit(request, user.id, "device.create", "device", device.id, device.name)
    return admin_device(device, runtime.settings, runtime.live_store)


@router.patch("/devices/{device_id}")
def update_device(device_id: str, payload: DeviceUpdate, request: Request) -> dict[str, object]:
    user, _ = _authorize(request, csrf=True)
    runtime = request.app.state.runtime
    updates = payload.model_dump(exclude_unset=True)
    mqtt_password = updates.pop("mqtt_password", None)
    try:
        with runtime.database.sessions.begin() as session:
            device = session.get(Device, device_id)
            if device is None:
                raise HTTPException(status_code=404, detail="Gerät nicht gefunden.")
            current = {
                "name": device.name,
                "technical_device_id": device.technical_device_id,
                "mqtt_topic_prefix": device.mqtt_topic_prefix,
                "mqtt_client_id": device.mqtt_client_id,
                "mqtt_username": device.mqtt_username,
                "device_type": device.device_type,
                "controllable": device.controllable,
                "relay_index": device.relay_index,
                "enabled": device.enabled,
                "sort_order": device.sort_order,
                "color": device.color,
            }
            validated = DeviceInput.model_validate(current | updates)
            for key, value in validated.model_dump(exclude={"mqtt_password"}).items():
                setattr(device, key, value)
            if mqtt_password:
                device.mqtt_password_hash = hash_mqtt_password(mqtt_password)
            device.updated_at = utc_now()
    except IntegrityError as error:
        raise HTTPException(
            status_code=409, detail="Geräte-ID, Topic oder Client-ID existiert bereits."
        ) from error
    _audit(request, user.id, "device.update", "device", device_id, json.dumps(sorted(updates)))
    return admin_device(device, runtime.settings, runtime.live_store)


@router.delete("/devices/{device_id}")
def delete_device(
    device_id: str, payload: DeleteDeviceInput, request: Request
) -> dict[str, object]:
    user, _ = _authorize(request, csrf=True)
    runtime = request.app.state.runtime
    with runtime.database.sessions.begin() as session:
        device = session.get(Device, device_id)
        if device is None:
            raise HTTPException(status_code=404, detail="Gerät nicht gefunden.")
        if payload.confirmation != device.name:
            raise HTTPException(
                status_code=400, detail="Bestätigung stimmt nicht mit dem Gerätenamen überein."
            )
        name = device.name
        if payload.delete_history:
            session.delete(device)
            action = "device.delete_permanently"
        else:
            device.enabled = False
            device.removed_at = utc_now()
            action = "device.remove"
    runtime.live_store.clear_device(device_id)
    _audit(request, user.id, action, "device", device_id, name)
    return {"deleted": payload.delete_history, "removed": not payload.delete_history}


@router.get("/users")
def list_users(request: Request) -> list[dict[str, object]]:
    _authorize(request)
    with request.app.state.runtime.database.sessions() as session:
        rows = session.scalars(select(User).order_by(User.username).limit(200)).all()
        return [
            {
                "id": row.id,
                "username": row.username,
                "enabled": row.enabled,
                "created_at": iso(row.created_at),
                "updated_at": iso(row.updated_at),
            }
            for row in rows
        ]


@router.post("/users", status_code=201)
def create_user(payload: UserInput, request: Request) -> dict[str, object]:
    actor, _ = _authorize(request, csrf=True)
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        enabled=payload.enabled,
    )
    try:
        with request.app.state.runtime.database.sessions.begin() as session:
            session.add(user)
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail="Benutzername ist bereits vergeben.") from error
    _audit(request, actor.id, "user.create", "user", user.id, user.username)
    return {"id": user.id, "username": user.username, "enabled": user.enabled}


@router.patch("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdate, request: Request) -> dict[str, object]:
    actor, _ = _authorize(request, csrf=True)
    with request.app.state.runtime.database.sessions.begin() as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden.")
        if payload.enabled is not None:
            if actor.id == user.id and not payload.enabled:
                raise HTTPException(
                    status_code=400, detail="Das eigene Konto kann nicht deaktiviert werden."
                )
            user.enabled = payload.enabled
        if payload.password:
            user.password_hash = hash_password(payload.password)
        user.updated_at = utc_now()
    _audit(request, actor.id, "user.update", "user", user_id)
    return {"id": user.id, "username": user.username, "enabled": user.enabled}


@router.get("/storage")
def storage(request: Request) -> dict[str, object]:
    _authorize(request)
    return request.app.state.runtime.cleanup.status()


@router.post("/storage/cleanup")
def cleanup(request: Request) -> dict[str, object]:
    user, _ = _authorize(request, csrf=True)
    result = request.app.state.runtime.cleanup.run_if_needed(force=True)
    _audit(request, user.id, "storage.cleanup_manual", "database", "sqlite")
    return result


@router.get("/system")
def system(request: Request) -> dict[str, object]:
    _authorize(request)
    runtime = request.app.state.runtime
    with runtime.database.sessions() as session:
        active_devices = session.scalar(
            select(func.count())
            .select_from(Device)
            .where(Device.enabled.is_(True), Device.removed_at.is_(None))
        )
    uptime = (utc_now() - runtime.started_at).total_seconds()
    return {
        "version": __version__,
        "started_at": runtime.started_at.isoformat(),
        "uptime_seconds": int(uptime),
        "mqtt_initialized": runtime.mqtt.initialized,
        "mqtt_connected": runtime.mqtt.connected,
        "mqtt_last_message": iso(runtime.mqtt.last_message_at),
        "database_ok": runtime.database.ping(),
        "websocket_connections": runtime.websockets.count,
        "active_devices": active_devices,
        "public_site": runtime.settings.public_base_url,
        "mqtt_public_endpoint": (
            f"{runtime.settings.mqtt_public_host}:{runtime.settings.mqtt_public_port}"
        ),
    }


@router.get("/mqtt")
def mqtt_settings(request: Request) -> dict[str, object]:
    _authorize(request)
    settings = request.app.state.runtime.settings
    return {
        "broker_hostname": settings.mqtt_host,
        "internal_port": settings.mqtt_port,
        "public_hostname": settings.mqtt_public_host,
        "public_tls_port": settings.mqtt_public_port,
        "tls_enabled_internal": settings.mqtt_tls,
        "topic_status": "ga/devices/<device-id>/status/em:0",
        "topic_online": "ga/devices/<device-id>/online",
        "server_client_id": settings.mqtt_client_id,
        "password_configured": settings.mqtt_password is not None,
        "note": "Die HTTPS-Website ist nicht die MQTT-Broker-Adresse.",
    }


@router.get("/versions")
def versions(request: Request) -> dict[str, object]:
    _authorize(request)
    changelog = (request.app.state.project_root / "CHANGELOG.md").read_text(encoding="utf-8")
    return {"version": __version__, "history": changelog[:50_000]}


def _generated_color(value: str) -> str:
    hue = (sum((index + 1) * ord(char) for index, char in enumerate(value)) % 360) / 360
    red, green, blue = colorsys.hls_to_rgb(hue, 0.58, 0.72)
    return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"
