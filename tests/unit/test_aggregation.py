"""
File: tests/unit/test_aggregation.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Verifies minute averages, extrema, totals, and duplicate suppression.
Changes:
- 0.1.0: Initial implementation.
"""

from datetime import UTC, datetime, timedelta

from app.services.aggregation import MinuteAggregate, MinuteAggregator
from app.services.measurement import Measurement


def measurement(at: datetime, value: float, fingerprint: str) -> Measurement:
    return Measurement(
        device_id="device-1",
        technical_device_id="shelly-1",
        received_at=at,
        measured_at=at,
        values={
            "current_l1": value,
            "current_l2": None,
            "current_l3": None,
            "current_total": value,
            "voltage_l1": 230,
            "voltage_l2": None,
            "voltage_l3": None,
            "power_l1": value * 230,
            "power_l2": None,
            "power_l3": None,
            "power_total": value * 230,
        },
        fingerprint=fingerprint,
    )


def test_minute_average_minimum_and_maximum() -> None:
    bucket = datetime(2026, 8, 3, 18, 5, tzinfo=UTC)
    aggregate = MinuteAggregate("device-1", bucket)
    aggregate.add(measurement(bucket, 1, "a"))
    aggregate.add(measurement(bucket + timedelta(seconds=10), 3, "b"))
    aggregate.add(measurement(bucket + timedelta(seconds=20), 2, "c"))
    columns = aggregate.columns()
    assert columns["sample_count"] == 3
    assert columns["current_l1_avg"] == 2
    assert columns["current_l1_min"] == 1
    assert columns["current_l1_max"] == 3
    assert columns["power_total_avg"] == 460


def test_duplicate_message_is_rejected_and_bucket_is_flushed_once() -> None:
    completed: list[MinuteAggregate] = []
    aggregator = MinuteAggregator(completed.append)
    start = datetime(2026, 8, 3, 18, 5, 10, tzinfo=UTC)
    sample = measurement(start, 1, "same")
    assert aggregator.ingest(sample) is True
    assert aggregator.ingest(sample) is False
    assert aggregator.flush_due(start + timedelta(minutes=1)) == 1
    assert aggregator.flush_due(start + timedelta(minutes=2)) == 0
    assert completed[0].sample_count == 1
