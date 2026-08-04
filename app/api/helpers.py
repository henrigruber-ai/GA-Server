"""
File: app/api/helpers.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Serializes database objects without exposing secret fields.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

from datetime import datetime

from app.config import Settings
from app.core.time import as_utc, utc_now
from app.db.models import Device
from app.services.live_store import LiveStore


def iso(value: datetime | None) -> str | None:
    return as_utc(value).isoformat() if value else None


def connection_state(last_seen_at: datetime | None, settings: Settings) -> str:
    if last_seen_at is None:
        return "offline"
    age = (utc_now() - as_utc(last_seen_at)).total_seconds()
    if age >= settings.offline_seconds:
        return "offline"
    if age >= settings.stale_seconds:
        return "stale"
    return "current"


def public_device(device: Device, settings: Settings, live_store: LiveStore) -> dict[str, object]:
    latest = live_store.latest().get(device.id)
    return {
        "id": device.id,
        "name": device.name,
        "color": device.color,
        "sort_order": device.sort_order,
        "status": connection_state(device.last_seen_at, settings),
        "is_online": device.is_online,
        "last_seen_at": iso(device.last_seen_at),
        "has_data": latest is not None or device.last_seen_at is not None,
    }


def admin_device(device: Device, settings: Settings, live_store: LiveStore) -> dict[str, object]:
    result = public_device(device, settings, live_store)
    result.update(
        {
            "technical_device_id": device.technical_device_id,
            "mqtt_topic_prefix": device.mqtt_topic_prefix,
            "mqtt_client_id": device.mqtt_client_id,
            "mqtt_username": device.mqtt_username,
            "mqtt_password_configured": device.mqtt_password_hash is not None,
            "enabled": device.enabled,
            "created_at": iso(device.created_at),
            "updated_at": iso(device.updated_at),
            "removed_at": iso(device.removed_at),
            "live": (
                live_store.latest()[device.id].public_dict()
                if device.id in live_store.latest()
                else None
            ),
        }
    )
    return result
