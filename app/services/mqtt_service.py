"""
File: app/services/mqtt_service.py
Version: 0.3.0
Date: 2026-08-06
Purpose: Routes Shelly and Tasmota MQTT messages into measurement and control services.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from datetime import datetime
from typing import Any

import paho.mqtt.client as mqtt
from sqlalchemy import select

from app.config import Settings
from app.core.time import utc_now
from app.db.database import Database
from app.db.models import Device
from app.services.aggregation import MinuteAggregator
from app.services.device_control import DeviceControlService
from app.services.live_store import LiveStore
from app.services.measurement import Measurement, ParseResult
from app.services.shelly_parser import parse_online, parse_status
from app.services.tasmota_parser import (
    TasmotaTopic,
    classify_topic,
    parse_lwt,
    parse_measurement,
    parse_power,
)
from app.services.websocket_manager import WebSocketManager

LOGGER = logging.getLogger(__name__)
TASMOTA_SUBSCRIPTIONS = (
    "tele/+/SENSOR",
    "tele/+/LWT",
    "stat/+/POWER",
    "stat/+/RESULT",
    "stat/+/STATUS10",
)


class MqttService:
    def __init__(
        self,
        database: Database,
        settings: Settings,
        live_store: LiveStore,
        aggregator: MinuteAggregator,
        websockets: WebSocketManager,
        control: DeviceControlService,
    ) -> None:
        self.database = database
        self.settings = settings
        self.live_store = live_store
        self.aggregator = aggregator
        self.websockets = websockets
        self.control = control
        self.client: mqtt.Client | None = None
        self.connected = False
        self.initialized = False
        self.last_message_at: datetime | None = None
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._warning_times: dict[str, float] = {}

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
        if not self.connected:
            LOGGER.error("MQTT connection rejected: %s", reason_code)
            return
        client.subscribe("ga/devices/+/status/em:0", qos=1)
        client.subscribe("ga/devices/+/online", qos=1)
        for topic in TASMOTA_SUBSCRIPTIONS:
            client.subscribe(topic, qos=1)
        self.request_tasmota_power_states()
        LOGGER.info("Connected to MQTT broker and subscribed to Shelly and Tasmota topics")

    def _on_disconnect(self, *_args: Any) -> None:
        self.connected = False
        LOGGER.warning("MQTT connection disconnected")

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        self.handle_message(message.topic, message.payload)

    def handle_message(
        self, topic: str, payload: bytes | str, received_at: datetime | None = None
    ) -> bool:
        try:
            return self._handle_message(topic, payload, received_at or utc_now())
        except Exception:
            LOGGER.exception("Unexpected MQTT callback error for topic %s", topic)
            return False

    def _handle_message(self, topic: str, payload: bytes | str, received_at: datetime) -> bool:
        classified = classify_topic(topic)
        if classified is not None:
            return self._handle_tasmota(classified, topic, payload, received_at)
        if topic.endswith("/online"):
            return self._handle_shelly_online(topic, payload, received_at)
        return self._handle_shelly_measurement(topic, payload, received_at)

    def _handle_shelly_online(
        self,
        topic: str,
        payload: bytes | str,
        received_at: datetime,
    ) -> bool:
        technical_id, online = parse_online(topic, payload)
        if technical_id is None or online is None:
            self._warn("shelly_online", "Ignored invalid Shelly online message on %s", topic)
            return False
        with self.database.sessions.begin() as session:
            device = session.scalar(
                select(Device).where(
                    Device.technical_device_id == technical_id,
                    Device.device_type == "shelly_pro_3em",
                )
            )
            if device is None:
                self._warn("unknown_shelly", "Ignored online state from unknown Shelly device")
                return False
            device.is_online = online
            device.last_seen_at = received_at
        return True

    def _handle_shelly_measurement(
        self,
        topic: str,
        payload: bytes | str,
        received_at: datetime,
    ) -> bool:
        parsed = parse_status(topic, payload, received_at)
        if not parsed.valid:
            self._warn(
                f"shelly:{parsed.error}",
                "Ignored Shelly MQTT message (%s) on %s",
                parsed.error,
                topic,
            )
            return False
        with self.database.sessions.begin() as session:
            device = session.scalar(
                select(Device).where(
                    Device.technical_device_id == parsed.technical_device_id,
                    Device.device_type == "shelly_pro_3em",
                    Device.enabled.is_(True),
                    Device.removed_at.is_(None),
                )
            )
            if device is None:
                self._warn("unknown_shelly", "Ignored measurement from unknown or inactive Shelly")
                return False
            device.last_seen_at = received_at
            device.is_online = True
        return self._ingest(device, parsed, received_at)

    def _handle_tasmota(
        self,
        classified: TasmotaTopic,
        topic: str,
        payload: bytes | str,
        received_at: datetime,
    ) -> bool:
        with self.database.sessions.begin() as session:
            device = session.scalar(
                select(Device).where(
                    Device.mqtt_topic_prefix == classified.device_topic,
                    Device.device_type == "tasmota_plug",
                    Device.enabled.is_(True),
                    Device.removed_at.is_(None),
                )
            )
            if device is None:
                self._warn("unknown_tasmota", "Ignored message from unknown Tasmota topic")
                return False
            session.expunge(device)

        if classified.kind == "LWT":
            _device_topic, online = parse_lwt(topic, payload)
            if online is None:
                self._warn("tasmota_lwt", "Ignored invalid Tasmota LWT message")
                return False
            accepted = self.control.observe_presence(
                device,
                online,
                received_at,
                source="lwt",
            )
            if accepted:
                self._update_device_presence(device.id, online, received_at)
            return True

        if classified.kind in {"POWER", "RESULT"}:
            result = parse_power(topic, payload, device.relay_index)
            if not result.valid:
                self._warn(
                    f"tasmota_power:{result.error}",
                    "Ignored invalid Tasmota POWER message (%s)",
                    result.error,
                )
                return False
            self.control.observe_power(device, bool(result.state), received_at)
            online = bool(self.control.store.snapshot(device.id)["online"])
            self._update_device_presence(device.id, online, received_at)
            self.last_message_at = received_at
            return True

        parsed = parse_measurement(topic, payload, received_at)
        if not parsed.valid:
            self._warn(
                f"tasmota_measurement:{parsed.error}",
                "Ignored invalid Tasmota measurement (%s)",
                parsed.error,
            )
            return False
        accepted = self.control.observe_presence(
            device,
            True,
            received_at,
            source="sensor",
        )
        if accepted:
            self._update_device_presence(device.id, True, received_at)
        return self._ingest(device, parsed, received_at)

    def _update_device_presence(
        self,
        device_id: str,
        online: bool,
        received_at: datetime,
    ) -> None:
        with self.database.sessions.begin() as session:
            device = session.get(Device, device_id)
            if device is not None:
                device.is_online = online
                device.last_seen_at = received_at

    def _ingest(self, device: Device, parsed: ParseResult, received_at: datetime) -> bool:
        measurement = Measurement(
            device_id=device.id,
            technical_device_id=device.technical_device_id,
            received_at=received_at,
            measured_at=parsed.measured_at or received_at,
            values=parsed.values or {},
            fingerprint=parsed.fingerprint or "",
        )
        if not self.aggregator.ingest(measurement):
            LOGGER.debug("Ignored duplicate measurement for %s", device.id)
            return False
        self.live_store.add(measurement)
        self.last_message_at = received_at
        public_measurement = measurement.public_dict()
        if device.device_type == "tasmota_plug":
            self.control.observe_measurement(device.id, public_measurement)
        if self._event_loop and self._event_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.websockets.broadcast({"type": "measurement", "data": public_measurement}),
                self._event_loop,
            )
        return True

    def publish_power(self, device: Device, desired_state: bool) -> bool:
        client = self.client
        if client is None or not self.connected:
            return False
        topic = f"cmnd/{device.mqtt_topic_prefix}/POWER"
        payload = "ON" if desired_state else "OFF"
        try:
            result = client.publish(topic, payload, qos=1, retain=False)
        except Exception:
            LOGGER.exception("Failed to publish Tasmota POWER command for device %s", device.id)
            return False
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def request_tasmota_power_states(self) -> int:
        client = self.client
        if client is None or not self.connected:
            return 0
        with self.database.sessions() as session:
            topics = session.scalars(
                select(Device.mqtt_topic_prefix).where(
                    Device.device_type == "tasmota_plug",
                    Device.enabled.is_(True),
                    Device.removed_at.is_(None),
                )
            ).all()
        published = 0
        for device_topic in topics:
            try:
                result = client.publish(
                    f"cmnd/{device_topic}/POWER",
                    "",
                    qos=1,
                    retain=False,
                )
            except Exception:
                LOGGER.exception("Failed to request Tasmota POWER state")
                continue
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                published += 1
        return published

    def _warn(self, key: str, message: str, *args: object) -> None:
        now = time.monotonic()
        if now - self._warning_times.get(key, 0) < 30:
            return
        self._warning_times[key] = now
        LOGGER.warning(message, *args)
