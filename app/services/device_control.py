"""
File: app/services/device_control.py
Version: 0.3.0
Date: 2026-08-06
Purpose: Publishes safe Tasmota power commands and resolves them only after confirmation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock, Timer
from typing import Protocol

from sqlalchemy import select

from app.core.time import as_utc, utc_now
from app.db.database import Database
from app.db.models import AuditLog, Device, User
from app.services.control_state import ControlStateStore, ControlTransition
from app.services.websocket_manager import WebSocketManager

LOGGER = logging.getLogger(__name__)


class MqttControlPublisher(Protocol):
    connected: bool

    def publish_power(self, device: Device, desired_state: bool) -> bool: ...


@dataclass(frozen=True, slots=True)
class ControlCommandContext:
    command_id: str
    device_id: str
    technical_device_id: str
    device_topic: str
    relay_index: int
    desired_state: bool
    user_id: str
    username: str
    requested_at: datetime


class DeviceControlError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class DeviceControlService:
    def __init__(
        self,
        database: Database,
        store: ControlStateStore,
        websockets: WebSocketManager,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.database = database
        self.store = store
        self.websockets = websockets
        self.timeout_seconds = timeout_seconds
        self.mqtt: MqttControlPublisher | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._commands: dict[str, ControlCommandContext] = {}
        self._timers: dict[str, Timer] = {}
        self._lock = RLock()

    def bind_mqtt(self, mqtt: MqttControlPublisher) -> None:
        self.mqtt = mqtt

    def set_event_loop(self, event_loop: asyncio.AbstractEventLoop) -> None:
        self._event_loop = event_loop

    def stop(self) -> None:
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
            self._commands.clear()
        for timer in timers:
            timer.cancel()

    def request_power(self, device_id: str, desired_state: bool, user: User) -> dict[str, object]:
        with self.database.sessions() as session:
            device = session.get(Device, device_id)
            if device is None or device.removed_at is not None or not device.enabled:
                raise DeviceControlError("device_not_found", "Gerät nicht gefunden.", 404)
            session.expunge(device)
        if device.device_type != "tasmota_plug":
            raise DeviceControlError(
                "unsupported_device_type",
                "Diese Geräteart unterstützt keine Schaltsteuerung.",
                409,
            )
        if not device.controllable:
            raise DeviceControlError("device_not_controllable", "Gerät ist nicht steuerbar.", 409)
        self.store.ensure(
            device.id,
            online=device.is_online,
            observed_at=device.last_seen_at,
        )
        if not bool(self.store.snapshot(device.id)["online"]):
            self._audit_rejected(device, user, desired_state, "device_offline")
            raise DeviceControlError("device_offline", "Gerät ist nicht erreichbar.", 409)
        if self.mqtt is None or not self.mqtt.connected:
            self._audit_rejected(device, user, desired_state, "mqtt_not_connected")
            raise DeviceControlError(
                "mqtt_not_connected",
                "Die MQTT-Verbindung ist nicht verfügbar.",
                503,
            )

        requested_at = utc_now()
        command_id = str(uuid.uuid4())
        deadline = requested_at + timedelta(seconds=self.timeout_seconds)
        try:
            self.store.begin(device.id, desired_state, command_id, deadline)
        except RuntimeError as error:
            self._audit_rejected(device, user, desired_state, str(error))
            raise DeviceControlError(
                "command_pending",
                "Für dieses Gerät wird bereits ein Befehl bestätigt.",
                409,
            ) from error
        context = ControlCommandContext(
            command_id=command_id,
            device_id=device.id,
            technical_device_id=device.technical_device_id,
            device_topic=device.mqtt_topic_prefix,
            relay_index=device.relay_index,
            desired_state=desired_state,
            user_id=user.id,
            username=user.username,
            requested_at=requested_at,
        )
        with self._lock:
            self._commands[command_id] = context
        timer = Timer(self.timeout_seconds, self._handle_timeout, args=(device.id, command_id))
        timer.daemon = True
        with self._lock:
            self._timers[command_id] = timer
        self._audit("device.power.requested", context)
        if not self.mqtt.publish_power(device, desired_state):
            self.store.reject(device.id, command_id, "publish_failed")
            self._finish_command(command_id)
            self._audit(
                "device.power.rejected",
                context,
                error="publish_failed",
                severity="warning",
            )
            self._broadcast(
                {
                    "type": "device_state",
                    "device_id": device.id,
                    "state": self.store.snapshot(device.id),
                }
            )
            raise DeviceControlError(
                "publish_failed",
                "Der Schaltbefehl konnte nicht veröffentlicht werden.",
                503,
            )
        with self._lock:
            timer_is_active = self._timers.get(command_id) is timer
        if timer_is_active:
            timer.start()
        snapshot = self.store.snapshot(device.id)
        self._broadcast({"type": "device_state", "device_id": device.id, "state": snapshot})
        return snapshot

    def observe_presence(
        self,
        device: Device,
        online: bool,
        observed_at: datetime,
        *,
        source: str,
    ) -> bool:
        accepted = self.store.mark_online(device.id, online, observed_at, source=source)
        if accepted:
            self._broadcast(
                {
                    "type": "device_state",
                    "device_id": device.id,
                    "state": self.store.snapshot(device.id),
                }
            )
        return accepted

    def observe_power(
        self,
        device: Device,
        confirmed_state: bool,
        observed_at: datetime,
    ) -> ControlTransition:
        self.store.mark_online(device.id, True, observed_at, source="power")
        transition = self.store.confirm(device.id, confirmed_state, observed_at)
        if transition.kind == "stale":
            return transition
        context = self._context(transition.command_id)
        if transition.kind == "confirmed" and context is not None:
            self._audit(
                "device.power.confirmed",
                context,
                confirmed_state=confirmed_state,
                latency_ms=self._latency_ms(context, observed_at),
            )
            self._finish_command(context.command_id)
        elif transition.kind == "conflict" and context is not None:
            self._audit(
                "device.power.conflict",
                context,
                confirmed_state=confirmed_state,
                latency_ms=self._latency_ms(context, observed_at),
                error="confirmation_conflict",
                severity="warning",
            )
            self._finish_command(context.command_id)
        self._broadcast(
            {
                "type": "device_state",
                "device_id": device.id,
                "state": self.store.snapshot(device.id),
            }
        )
        return transition

    def observe_measurement(self, device_id: str, measurement: dict[str, object]) -> None:
        self._broadcast(
            {
                "type": "device_measurement",
                "device_id": device_id,
                "data": measurement,
            }
        )

    def snapshot_devices(self) -> list[dict[str, object]]:
        from app.api.helpers import iso

        with self.database.sessions() as session:
            devices = session.scalars(
                select(Device)
                .where(
                    Device.device_type == "tasmota_plug",
                    Device.enabled.is_(True),
                    Device.removed_at.is_(None),
                )
                .order_by(Device.sort_order, Device.name)
                .limit(200)
            ).all()
            output = []
            for device in devices:
                self.store.ensure(
                    device.id,
                    online=device.is_online,
                    observed_at=device.last_seen_at,
                )
                output.append(
                    {
                        "id": device.id,
                        "name": device.name,
                        "technical_device_id": device.technical_device_id,
                        "controllable": device.controllable,
                        "relay_index": device.relay_index,
                        "last_seen_at": iso(device.last_seen_at),
                        "control": self.store.snapshot(device.id),
                    }
                )
            return output

    def _handle_timeout(self, device_id: str, command_id: str) -> None:
        transition = self.store.timeout(
            device_id,
            command_id,
            utc_now() + timedelta(milliseconds=10),
        )
        if transition is None:
            return
        context = self._context(command_id)
        if context is not None:
            self._audit(
                "device.power.timeout",
                context,
                confirmed_state=transition.confirmed_state,
                error="confirmation_timeout",
                severity="warning",
            )
        self._finish_command(command_id)
        self._broadcast(
            {
                "type": "device_state",
                "device_id": device_id,
                "state": self.store.snapshot(device_id),
            }
        )

    def _audit_rejected(
        self,
        device: Device,
        user: User,
        desired_state: bool,
        error: str,
    ) -> None:
        context = ControlCommandContext(
            command_id="",
            device_id=device.id,
            technical_device_id=device.technical_device_id,
            device_topic=device.mqtt_topic_prefix,
            relay_index=device.relay_index,
            desired_state=desired_state,
            user_id=user.id,
            username=user.username,
            requested_at=utc_now(),
        )
        self._audit("device.power.rejected", context, error=error, severity="warning")

    def _audit(
        self,
        action: str,
        context: ControlCommandContext,
        *,
        confirmed_state: bool | None = None,
        latency_ms: int | None = None,
        error: str | None = None,
        severity: str = "info",
    ) -> None:
        details = {
            "username": context.username,
            "technical_device_id": context.technical_device_id,
            "topic": context.device_topic,
            "relay": context.relay_index,
            "desired_state": context.desired_state,
            "confirmed_state": confirmed_state,
            "command_id": context.command_id or None,
            "requested_at": context.requested_at.isoformat(),
            "latency_ms": latency_ms,
            "error": error,
        }
        with self.database.sessions.begin() as session:
            session.add(
                AuditLog(
                    user_id=context.user_id,
                    action=action,
                    target_type="device",
                    target_id=context.device_id,
                    details=json.dumps(details, separators=(",", ":"), ensure_ascii=False),
                    severity=severity,
                )
            )

    def _context(self, command_id: str | None) -> ControlCommandContext | None:
        if command_id is None:
            return None
        with self._lock:
            return self._commands.get(command_id)

    def _finish_command(self, command_id: str) -> None:
        with self._lock:
            timer = self._timers.pop(command_id, None)
            self._commands.pop(command_id, None)
        if timer is not None:
            timer.cancel()

    @staticmethod
    def _latency_ms(context: ControlCommandContext, observed_at: datetime) -> int:
        return max(0, round((as_utc(observed_at) - context.requested_at).total_seconds() * 1000))

    def _broadcast(self, message: dict[str, object]) -> None:
        loop = self._event_loop
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self.websockets.broadcast(message), loop)
