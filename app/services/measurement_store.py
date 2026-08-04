"""
File: app/services/measurement_store.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Upserts completed minute aggregates and refreshes bounded rolling statistics.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import cast

from sqlalchemy import delete, select

from app.core.time import utc_now
from app.db.database import Database
from app.db.models import DeviceWindowStat, MinuteMeasurement
from app.services.aggregation import MinuteAggregate
from app.services.measurement import METRIC_KEYS

WINDOWS = {"hour": timedelta(hours=1), "day": timedelta(days=1), "week": timedelta(days=7)}


class MeasurementStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def save(self, aggregate: MinuteAggregate) -> None:
        values = aggregate.columns()
        with self.database.sessions.begin() as session:
            existing = session.scalar(
                select(MinuteMeasurement).where(
                    MinuteMeasurement.device_id == aggregate.device_id,
                    MinuteMeasurement.bucket_start == aggregate.bucket_start,
                )
            )
            if existing is None:
                session.add(MinuteMeasurement(**values))
            else:
                self._merge(existing, values)
        self.refresh_stats(aggregate.device_id)

    @staticmethod
    def _merge(existing: MinuteMeasurement, incoming: dict[str, object]) -> None:
        old_count = existing.sample_count
        new_count = cast(int, incoming["sample_count"])
        for metric in METRIC_KEYS:
            old_avg = getattr(existing, f"{metric}_avg")
            new_avg = cast(float | None, incoming[f"{metric}_avg"])
            if old_avg is None:
                merged_avg = new_avg
            elif new_avg is None:
                merged_avg = old_avg
            else:
                merged_avg = (old_avg * old_count + new_avg * new_count) / (old_count + new_count)
            setattr(existing, f"{metric}_avg", merged_avg)
            old_min = getattr(existing, f"{metric}_min")
            new_min = cast(float | None, incoming[f"{metric}_min"])
            setattr(
                existing,
                f"{metric}_min",
                new_min
                if old_min is None
                else old_min
                if new_min is None
                else min(old_min, new_min),
            )
            old_max = getattr(existing, f"{metric}_max")
            new_max = cast(float | None, incoming[f"{metric}_max"])
            setattr(
                existing,
                f"{metric}_max",
                new_max
                if old_max is None
                else old_max
                if new_max is None
                else max(old_max, new_max),
            )
        existing.sample_count = old_count + new_count

    def refresh_stats(self, device_id: str) -> None:
        now = utc_now()
        with self.database.sessions.begin() as session:
            for window_type, duration in WINDOWS.items():
                rows = session.scalars(
                    select(MinuteMeasurement)
                    .where(
                        MinuteMeasurement.device_id == device_id,
                        MinuteMeasurement.bucket_start >= now - duration,
                    )
                    .order_by(MinuteMeasurement.bucket_start)
                    .limit(10_080)
                ).all()
                for metric in METRIC_KEYS:
                    metric_name, phase = metric.split("_", 1)
                    points = [
                        (row.bucket_start, getattr(row, f"{metric}_avg"))
                        for row in rows
                        if getattr(row, f"{metric}_avg") is not None
                    ]
                    key_filter = (
                        DeviceWindowStat.device_id == device_id,
                        DeviceWindowStat.window_type == window_type,
                        DeviceWindowStat.metric == metric_name,
                        DeviceWindowStat.phase == phase,
                    )
                    stat = session.scalar(select(DeviceWindowStat).where(*key_filter))
                    if not points:
                        if stat is not None:
                            session.execute(delete(DeviceWindowStat).where(*key_filter))
                        continue
                    minimum_point = min(points, key=lambda item: item[1])
                    maximum_point = max(points, key=lambda item: item[1])
                    if stat is None:
                        stat = DeviceWindowStat(
                            device_id=device_id,
                            window_type=window_type,
                            metric=metric_name,
                            phase=phase,
                        )
                        session.add(stat)
                    stat.minimum = minimum_point[1]
                    stat.minimum_timestamp = minimum_point[0]
                    stat.maximum = maximum_point[1]
                    stat.maximum_timestamp = maximum_point[0]
                    stat.updated_at = now
