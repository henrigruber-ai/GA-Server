"""
File: app/services/measurement.py
Version: 0.2.0
Date: 2026-08-04
Purpose: Defines validated in-memory measurement records shared across services.
Changes:
- 0.1.0: Initial implementation.
- 0.2.0: Publishes the canonical set of technically available measurement series.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

METRIC_KEYS = (
    "current_l1",
    "current_l2",
    "current_l3",
    "current_total",
    "voltage_l1",
    "voltage_l2",
    "voltage_l3",
    "power_l1",
    "power_l2",
    "power_l3",
    "power_total",
)

SERIES_DEFINITIONS = {
    "current": ("l1", "l2", "l3", "total"),
    "voltage": ("l1", "l2", "l3"),
    "power": ("l1", "l2", "l3", "total"),
}


@dataclass(frozen=True, slots=True)
class Measurement:
    device_id: str
    technical_device_id: str
    received_at: datetime
    measured_at: datetime
    values: dict[str, float | None]
    fingerprint: str

    def public_dict(self) -> dict[str, object]:
        return {
            "device_id": self.device_id,
            "technical_device_id": self.technical_device_id,
            "received_at": self.received_at.isoformat(),
            "measured_at": self.measured_at.isoformat(),
            "values": self.values,
        }


@dataclass(frozen=True, slots=True)
class ParseResult:
    technical_device_id: str | None
    measured_at: datetime | None
    values: dict[str, float | None] | None
    fingerprint: str | None
    error: str | None = None

    @property
    def valid(self) -> bool:
        return self.error is None and self.values is not None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)
