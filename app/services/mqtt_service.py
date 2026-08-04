"""
File: app/services/mqtt_service.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Receives Shelly MQTT messages safely and feeds live and minute services.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from datetime import datetime
from typing import Any

import paho.mqtt.client as mqtt
from sqlalchemy import select

from app.config import Settings
from app.core.time import utc_now
from app.db.database import Database
from app.db.models import Device
from app.services.aggregation import MinuteAggregator
from app.services.live_store import LiveStore
from app.services.measurement import Measurement
from app.services.shelly_parser import parse_online, parse_status
from app.services.websocket_manager import WebSocketManager

LOGGER = logging.getLogger(__name__)


class MqttService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        live_store: LiveStore,
        aggregator: MinuteAggregator,
        websockets: WebSocketManager,
    ) -> None:
        self.database = database
        self.settings = settings
        self.live_store = live_store
        self.aggregator = aggregator
        self.websockets = websockets
        self.client: mqtt.Client | None = None
        self.connected = False
        self.initialized = False
        self.last_message_at: datetime | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def start(self, event_loop: asyncio.AbstractEventLoop) -> None:
        self._event_loop = event_loop
        self.initialized = True
        if not self.settings.mqtt_enabled:
            LOGGER.info("MQTT is disabled by configuration")
            return
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.settings.mqtt_client_id,
        )
        if self.settings.mqtt_username:
            client.username_pw_set(self.settings.mqtt_username, self.settings.mqtt_password)
        if self.settings.mqtt_tls:
            client.tls_set(
                ca_certs=self.settings.mqtt_ca_file,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        self.client = client
        try:
            client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, keepalive=60)
            client.loop_start()
        except Exception:
            LOGGER.exception("Could not initialize MQTT connection")

    def stop(self) -> None:
        self.aggregator.flush_due(force=True)
        if self.client is not None:
            try:
                self.client.disconnect()
            finally:
                self.client.loop_stop()
        self.connected = False

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: Any,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        self.connected = reason_code == 0
        if self.connected:
            client.subscribe("ga/devices/+/status/em:0", qos=1)
            client.subscribe("ga/devices/+/online", qos=1)
            LOGGER.info("Connected to MQTT broker and subscribed to GA device topics")
        else:
            LOGGER.error("MQTT connection rejected: %s", reason_code)

    def _on_disconnect(self, *_args: Any) -> None:
        self.connected = False
        LOGGER.warning("MQTT connection disconnected")

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        self.handle_message(message.topic, message.payload)

    def handle_message(
        self, topic: str, payload: bytes | str, received_at: datetime | None = None
    ) -> bool:
        received_at = received_at or utc_now()
        if topic.endswith("/online"):
            technical_id, online = parse_online(topic, payload)
            if technical_id is None or online is None:
                LOGGER.warning("Ignored invalid online message on topic %s", topic)
                return False
            with self.database.sessions.begin() as session:
                device = session.scalar(
                    select(Device).where(Device.technical_device_id == technical_id)
                )
                if device is None:
                    LOGGER.warning("Ignored online state from unknown device %s", technical_id)
                    return False
                device.is_online = online
                device.last_seen_at = received_at
            return True
        parsed = parse_status(topic, payload, received_at)
        if not parsed.valid:
            LOGGER.warning("Ignored MQTT message: %s on %s", parsed.error, topic)
            return False
        with self.database.sessions.begin() as session:
            device = session.scalar(
                select(Device).where(
                    Device.technical_device_id == parsed.technical_device_id,
                    Device.enabled.is_(True),
                    Device.removed_at.is_(None),
                )
            )
            if device is None:
                LOGGER.warning("Ignored measurement from unknown or inactive device")
                return False
            device.last_seen_at = received_at
            device.is_online = True
            device_id = device.id
        measurement = Measurement(
            device_id=device_id,
            technical_device_id=parsed.technical_device_id or "",
            received_at=received_at,
            measured_at=parsed.measured_at or received_at,
            values=parsed.values or {},
            fingerprint=parsed.fingerprint or "",
        )
        if not self.aggregator.ingest(measurement):
            LOGGER.debug("Ignored duplicate measurement for %s", device_id)
            return False
        self.live_store.add(measurement)
        self.last_message_at = received_at
        if self._event_loop and self._event_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.websockets.broadcast(
                    {"type": "measurement", "data": measurement.public_dict()}
                ),
                self._event_loop,
            )
        return True
