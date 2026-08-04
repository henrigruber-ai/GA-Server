"""
File: tests/integration/test_storage_and_stats.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Verifies rolling windows and oldest-first cleanup while preserving devices and users.
Changes:
- 0.1.0: Initial implementation.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.database import Database
from app.db.models import Device, DeviceWindowStat, MinuteMeasurement, User
from app.services.aggregation import MinuteAggregate
from app.services.cleanup import CleanupService
from app.services.measurement import Measurement
from app.services.measurement_store import MeasurementStore

pytestmark = pytest.mark.integration


def add_value(aggregate: MinuteAggregate, value: float) -> None:
    aggregate.add(
        Measurement(
            device_id=aggregate.device_id,
            technical_device_id="meter",
            received_at=aggregate.bucket_start,
            measured_at=aggregate.bucket_start,
            values={"power_total": value},
            fingerprint=str(value),
        )
    )


def test_hour_day_and_week_stats(app_settings: object) -> None:
    database = Database(app_settings.database_url)
    database.initialize()
    with database.sessions.begin() as session:
        device = Device(
            name="Meter",
            technical_device_id="meter",
            mqtt_topic_prefix="ga/devices/meter",
            mqtt_client_id="meter",
            color="#123456",
        )
        session.add(device)
    store = MeasurementStore(database)
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    for offset, value in (
        (timedelta(minutes=30), 30),
        (timedelta(hours=2), 20),
        (timedelta(days=2), 10),
    ):
        aggregate = MinuteAggregate(device.id, now - offset)
        add_value(aggregate, value)
        store.save(aggregate)
    with database.sessions() as session:
        stats = session.scalars(
            select(DeviceWindowStat).where(
                DeviceWindowStat.metric == "power", DeviceWindowStat.phase == "total"
            )
        ).all()
        by_window = {stat.window_type: (stat.minimum, stat.maximum) for stat in stats}
    assert by_window["hour"] == (30, 30)
    assert by_window["day"] == (20, 30)
    assert by_window["week"] == (10, 30)


def test_cleanup_deletes_oldest_first_and_preserves_configuration(app_settings: object) -> None:
    database = Database(app_settings.database_url)
    database.initialize()
    with database.sessions.begin() as session:
        device = Device(
            name="Meter",
            technical_device_id="meter",
            mqtt_topic_prefix="ga/devices/meter",
            mqtt_client_id="meter",
            color="#123456",
        )
        user = User(username="admin", password_hash="not-a-real-hash")
        session.add_all([device, user])
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    with database.sessions.begin() as session:
        for age in (30, 20, 10):
            session.add(
                MinuteMeasurement(
                    device_id=device.id,
                    bucket_start=now - timedelta(days=age),
                    sample_count=1,
                    power_total_avg=float(age),
                    power_total_min=float(age),
                    power_total_max=float(age),
                )
            )
    cleanup = CleanupService(database, app_settings, batch_size=2)
    result = cleanup.run_if_needed(force=True)
    assert result["deleted"] == 2
    with database.sessions() as session:
        remaining = session.scalars(
            select(MinuteMeasurement).order_by(MinuteMeasurement.bucket_start)
        ).all()
        assert [row.power_total_avg for row in remaining] == [10]
        assert session.scalar(select(func.count()).select_from(Device)) == 1
        assert session.scalar(select(func.count()).select_from(User)) == 1
