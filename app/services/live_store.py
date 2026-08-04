"""
File: app/services/live_store.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Maintains bounded volatile live samples and latest values per device.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta
from threading import RLock

from app.core.time import utc_now
from app.services.measurement import Measurement


class LiveStore:
    def __init__(self, max_samples: int = 3600, max_minutes: int = 15) -> None:
        self.max_samples = max_samples
        self.max_age = timedelta(minutes=max_minutes)
        self._samples: dict[str, deque[Measurement]] = defaultdict(
            lambda: deque(maxlen=self.max_samples)
        )
        self._latest: dict[str, Measurement] = {}
        self._lock = RLock()

    def add(self, measurement: Measurement) -> None:
        with self._lock:
            samples = self._samples[measurement.device_id]
            samples.append(measurement)
            self._latest[measurement.device_id] = measurement
            cutoff = utc_now() - self.max_age
            while samples and samples[0].received_at < cutoff:
                samples.popleft()

    def latest(self) -> dict[str, Measurement]:
        with self._lock:
            return dict(self._latest)

    def samples(self, device_id: str) -> list[Measurement]:
        with self._lock:
            return list(self._samples.get(device_id, ()))

    def clear_device(self, device_id: str) -> None:
        with self._lock:
            self._latest.pop(device_id, None)
            self._samples.pop(device_id, None)
