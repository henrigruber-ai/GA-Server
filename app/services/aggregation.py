"""
File: app/services/aggregation.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Aggregates volatile samples into one min/avg/max record per device and UTC minute.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import RLock

from app.core.time import minute_bucket, utc_now
from app.services.measurement import METRIC_KEYS, Measurement


@dataclass(slots=True)
class RunningMetric:
    count: int = 0
    total: float = 0
    minimum: float | None = None
    maximum: float | None = None

    def add(self, value: float | None) -> None:
        if value is None:
            return
        self.count += 1
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def columns(self, name: str) -> dict[str, float | None]:
        average = self.total / self.count if self.count else None
        return {f"{name}_avg": average, f"{name}_min": self.minimum, f"{name}_max": self.maximum}


@dataclass(slots=True)
class MinuteAggregate:
    device_id: str
    bucket_start: datetime
    sample_count: int = 0
    metrics: dict[str, RunningMetric] = field(
        default_factory=lambda: {key: RunningMetric() for key in METRIC_KEYS}
    )

    def add(self, measurement: Measurement) -> None:
        self.sample_count += 1
        for key in METRIC_KEYS:
            self.metrics[key].add(measurement.values.get(key))

    def columns(self) -> dict[str, object]:
        values: dict[str, object] = {
            "device_id": self.device_id,
            "bucket_start": self.bucket_start,
            "sample_count": self.sample_count,
        }
        for name, metric in self.metrics.items():
            values.update(metric.columns(name))
        return values


class MinuteAggregator:
    def __init__(
        self,
        on_complete: Callable[[MinuteAggregate], None],
        duplicate_ttl_seconds: int = 180,
    ) -> None:
        self.on_complete = on_complete
        self.duplicate_ttl = timedelta(seconds=duplicate_ttl_seconds)
        self._buckets: dict[tuple[str, datetime], MinuteAggregate] = {}
        self._fingerprints: dict[str, deque[tuple[datetime, str]]] = {}
        self._lock = RLock()

    def ingest(self, measurement: Measurement) -> bool:
        with self._lock:
            fingerprints = self._fingerprints.setdefault(measurement.device_id, deque(maxlen=2048))
            cutoff = measurement.received_at - self.duplicate_ttl
            while fingerprints and fingerprints[0][0] < cutoff:
                fingerprints.popleft()
            if any(value == measurement.fingerprint for _, value in fingerprints):
                return False
            fingerprints.append((measurement.received_at, measurement.fingerprint))
            key = (measurement.device_id, minute_bucket(measurement.measured_at))
            aggregate = self._buckets.setdefault(key, MinuteAggregate(*key))
            aggregate.add(measurement)
        self.flush_due(measurement.received_at)
        return True

    def flush_due(self, now: datetime | None = None, *, force: bool = False) -> int:
        threshold = minute_bucket(now or utc_now())
        completed: list[MinuteAggregate] = []
        with self._lock:
            for key, aggregate in list(self._buckets.items()):
                if force or aggregate.bucket_start < threshold:
                    completed.append(self._buckets.pop(key))
        for aggregate in sorted(completed, key=lambda item: item.bucket_start):
            self.on_complete(aggregate)
        return len(completed)
