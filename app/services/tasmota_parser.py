"""
File: app/services/tasmota_parser.py
Version: 0.3.0
Date: 2026-08-06
Purpose: Classifies and defensively parses supported Tasmota MQTT messages.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from app.core.time import as_utc
from app.services.measurement import METRIC_KEYS, ParseResult

TASMOTA_TOPIC = re.compile(
    r"^(?P<namespace>tele|stat)/(?P<device>[^/]+)/"
    r"(?P<kind>SENSOR|LWT|STATUS10|POWER|RESULT)$"
)
VALID_TOPIC_COMBINATIONS = {
    ("tele", "SENSOR"),
    ("tele", "LWT"),
    ("stat", "STATUS10"),
    ("stat", "POWER"),
    ("stat", "RESULT"),
}


@dataclass(frozen=True, slots=True)
class TasmotaTopic:
    namespace: Literal["tele", "stat"]
    device_topic: str
    kind: Literal["SENSOR", "LWT", "STATUS10", "POWER", "RESULT"]


@dataclass(frozen=True, slots=True)
class PowerResult:
    device_topic: str | None
    state: bool | None
    error: str | None = None

    @property
    def valid(self) -> bool:
        return self.error is None and self.device_topic is not None and self.state is not None


def classify_topic(topic: str) -> TasmotaTopic | None:
    match = TASMOTA_TOPIC.fullmatch(topic)
    if match is None:
        return None
    namespace = match.group("namespace")
    kind = match.group("kind")
    if (namespace, kind) not in VALID_TOPIC_COMBINATIONS:
        return None
    return TasmotaTopic(namespace, match.group("device"), kind)  # type: ignore[arg-type]


def _decode_json(payload: bytes | str) -> dict[str, Any] | None:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _payload_time(data: dict[str, Any], received_at: datetime) -> datetime:
    candidate = data.get("Time")
    if not isinstance(candidate, str):
        return received_at
    try:
        parsed = as_utc(datetime.fromisoformat(candidate.replace("Z", "+00:00")))
    except ValueError:
        return received_at
    return parsed if abs(parsed - received_at) <= timedelta(minutes=5) else received_at


def parse_measurement(topic: str, payload: bytes | str, received_at: datetime) -> ParseResult:
    classified = classify_topic(topic)
    if classified is None or classified.kind not in {"SENSOR", "STATUS10"}:
        return ParseResult(None, None, None, None, "invalid_topic")
    decoded = _decode_json(payload)
    if decoded is None:
        return ParseResult(classified.device_topic, None, None, None, "invalid_json")
    sensor = decoded.get("StatusSNS") if classified.kind == "STATUS10" else decoded
    if not isinstance(sensor, dict):
        return ParseResult(classified.device_topic, None, None, None, "missing_sensor_status")
    energy = sensor.get("ENERGY")
    if not isinstance(energy, dict):
        return ParseResult(classified.device_topic, None, None, None, "missing_energy")

    current = _number(energy.get("Current"))
    voltage = _number(energy.get("Voltage"))
    power = _number(energy.get("Power"))
    values: dict[str, float | None] = {key: None for key in METRIC_KEYS}
    values.update(
        {
            "current_l1": current,
            "current_total": current,
            "voltage_l1": voltage,
            "power_l1": power,
            "power_total": power,
        }
    )
    if all(value is None for value in values.values()):
        return ParseResult(classified.device_topic, None, None, None, "no_valid_values")

    canonical = json.dumps(
        decoded,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    fingerprint = hashlib.sha256(topic.encode("utf-8") + b"\0" + canonical).hexdigest()
    return ParseResult(
        technical_device_id=classified.device_topic,
        measured_at=_payload_time(sensor, as_utc(received_at)),
        values=values,
        fingerprint=fingerprint,
    )


def parse_lwt(topic: str, payload: bytes | str) -> tuple[str | None, bool | None]:
    classified = classify_topic(topic)
    if classified is None or classified.kind != "LWT":
        return None, None
    raw = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else payload
    normalized = raw.strip().strip('"').lower()
    if normalized == "online":
        return classified.device_topic, True
    if normalized == "offline":
        return classified.device_topic, False
    return classified.device_topic, None


def parse_power(topic: str, payload: bytes | str, relay_index: int = 1) -> PowerResult:
    classified = classify_topic(topic)
    if classified is None or classified.kind not in {"POWER", "RESULT"}:
        return PowerResult(None, None, "invalid_topic")
    if classified.kind == "POWER":
        raw = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else payload
        candidate: object = raw.strip().strip('"')
    else:
        decoded = _decode_json(payload)
        if decoded is None:
            return PowerResult(classified.device_topic, None, "invalid_json")
        candidate = decoded.get("POWER" if relay_index == 1 else f"POWER{relay_index}")
    if not isinstance(candidate, str):
        return PowerResult(classified.device_topic, None, "invalid_power")
    normalized = candidate.strip().upper()
    if normalized == "ON":
        return PowerResult(classified.device_topic, True)
    if normalized == "OFF":
        return PowerResult(classified.device_topic, False)
    return PowerResult(classified.device_topic, None, "invalid_power")
