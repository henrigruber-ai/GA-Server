"""
File: tests/unit/test_live_store.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Verifies that the volatile live buffer remains quantity-bounded.
Changes:
- 0.1.0: Initial implementation.
"""

from datetime import UTC, datetime, timedelta

from app.services.live_store import LiveStore
from app.services.measurement import Measurement


def test_live_store_is_bounded() -> None:
    store = LiveStore(max_samples=2, max_minutes=60)
    now = datetime.now(UTC)
    for index in range(3):
        sample = Measurement(
            device_id="d",
            technical_device_id="t",
            received_at=now + timedelta(seconds=index),
            measured_at=now + timedelta(seconds=index),
            values={"power_total": float(index)},
            fingerprint=str(index),
        )
        store.add(sample)
    assert len(store.samples("d")) == 2
    assert store.latest()["d"].values["power_total"] == 2
