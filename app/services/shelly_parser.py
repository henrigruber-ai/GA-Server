"""
File: app/services/shelly_parser.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Defensively parses Shelly Pro 3EM status topics and numeric payload fields.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.time import as_utc
from app.services.measurement import METRIC_KEYS, ParseResult

STATUS_TOPIC = re.compile(r"^ga/devices/(?P<device>[^/]+)/status/em:0$")
ONLINE_TOPIC = re.compile(r"^ga/devices/(?P<device>[^/]+)/online$")

FIELD_MAP = {
    "a_current": "current_l1",
    "b_current": "current_l2",
    "c_current": "current_l3",
    "total_current": "current_total",
    "a_voltage": "voltage_l1",
    "b_voltage": "voltage_l2",
    "c_voltage": "voltage_l3",
    "a_act_power": "power_l1",
    "b_act_power": "power_l2",
    "c_act_power": "power_l3",
    "total_act_power": "power_total",
}


def topic_device_id(topic: str, *, online: bool = False) -> str | None:
    match = (ONLINE_TOPIC if online else STATUS_TOPIC).fullmatch(topic)
    return match.group("device") if match else None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _payload_time(data: dict[str, Any], received_at: datetime) -> datetime:
    candidate = data.get("ts", data.get("timestamp"))
    if isinstance(candidate, bool) or not isinstance(candidate, (int, float, str)):
        return received_at
    try:
        if isinstance(candidate, str):
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromtimestamp(float(candidate), tz=UTC)
        parsed = as_utc(parsed)
    except (TypeError, ValueError, OSError):
        return received_at
    return parsed if abs(parsed - received_at) <= timedelta(minutes=5) else received_at


def parse_status(topic: str, payload: bytes | str, received_at: datetime) -> ParseResult:
    technical_id = topic_device_id(topic)
    if technical_id is None:
        return ParseResult(None, None, None, None, "invalid_topic")
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return ParseResult(technical_id, None, None, None, "invalid_json")
    if not isinstance(decoded, dict):
        return ParseResult(technical_id, None, None, None, "invalid_payload")
    body = decoded.get("em:0", decoded)
    if not isinstance(body, dict):
        return ParseResult(technical_id, None, None, None, "missing_em_status")
    values: dict[str, float | None] = {key: None for key in METRIC_KEYS}
    for shelly_key, metric_key in FIELD_MAP.items():
        values[metric_key] = _number(body.get(shelly_key))
    if values["current_total"] is None:
        phases = [values[f"current_l{phase}"] for phase in (1, 2, 3)]
        if all(value is not None for value in phases):
            values["current_total"] = sum(value for value in phases if value is not None)
    if values["power_total"] is None:
        phases = [values[f"power_l{phase}"] for phase in (1, 2, 3)]
        if all(value is not None for value in phases):
            values["power_total"] = sum(value for value in phases if value is not None)
    if all(value is None for value in values.values()):
        return ParseResult(technical_id, None, None, None, "no_valid_values")
    fingerprint = hashlib.sha256(
        topic.encode("utf-8") + b"\0" + json.dumps(decoded, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return ParseResult(
        technical_device_id=technical_id,
        measured_at=_payload_time(body, as_utc(received_at)),
        values=values,
        fingerprint=fingerprint,
    )


def parse_online(topic: str, payload: bytes | str) -> tuple[str | None, bool | None]:
    technical_id = topic_device_id(topic, online=True)
    if technical_id is None:
        return None, None
    raw = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else payload
    normalized = raw.strip().strip('"').lower()
    if normalized in {"true", "1", "online", "yes"}:
        return technical_id, True
    if normalized in {"false", "0", "offline", "no"}:
        return technical_id, False
    return technical_id, None
