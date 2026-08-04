"""
File: app/api/routes_public.py
Version: 0.2.0
Date: 2026-08-04
Purpose: Provides bounded, read-only public device, live, history, stats, and WebSocket APIs.
Changes:
- 0.1.0: Initial implementation.
- 0.2.0: Adds one bundled history response for all requested measurement series.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.helpers import iso, public_device
from app.core.time import utc_now
from app.db.models import Device, DeviceWindowStat, MinuteMeasurement
from app.services.measurement import SERIES_DEFINITIONS

router = APIRouter(prefix="/api/public", tags=["public"])
VALID_SERIES = {metric: set(phases) for metric, phases in SERIES_DEFINITIONS.items()}


@router.get("/devices")
def devices(request: Request) -> list[dict[str, object]]:
    runtime = request.app.state.runtime
    with runtime.database.sessions() as session:
        rows = session.scalars(
            select(Device)
            .where(Device.enabled.is_(True), Device.removed_at.is_(None))
            .order_by(Device.sort_order, Device.name)
            .limit(200)
        ).all()
        return [public_device(row, runtime.settings, runtime.live_store) for row in rows]


@router.get("/live")
def live(request: Request) -> dict[str, object]:
    runtime = request.app.state.runtime
    latest = runtime.live_store.latest()
    return {
        "server_time": utc_now().isoformat(),
        "measurements": [measurement.public_dict() for measurement in latest.values()],
    }


@router.get("/history")
def history(
    request: Request,
    metric: str = Query(default="power", pattern="^(current|voltage|power)$"),
    phase: str = Query(default="total", pattern="^(l1|l2|l3|total)$"),
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    max_points: int = Query(default=1440, ge=60, le=2880),
) -> dict[str, object]:
    if phase not in VALID_SERIES[metric]:
        return {"metric": metric, "phase": phase, "series": [], "error": "phase_not_available"}
    now = utc_now()
    try:
        end = min(now, _parse_time(to_time) if to_time else now)
        start = _parse_time(from_time) if from_time else end - timedelta(hours=24)
    except ValueError:
        return {"metric": metric, "phase": phase, "series": [], "error": "invalid_time"}
    start = max(start, end - timedelta(days=8))
    column = getattr(MinuteMeasurement, f"{metric}_{phase}_avg")
    runtime = request.app.state.runtime
    with runtime.database.sessions() as session:
        enabled_devices = session.scalars(
            select(Device)
            .where(Device.enabled.is_(True), Device.removed_at.is_(None))
            .order_by(Device.sort_order)
            .limit(200)
        ).all()
        output: list[dict[str, object]] = []
        for device in enabled_devices:
            rows = session.execute(
                select(MinuteMeasurement.bucket_start, column)
                .where(
                    MinuteMeasurement.device_id == device.id,
                    MinuteMeasurement.bucket_start >= start,
                    MinuteMeasurement.bucket_start <= end,
                )
                .order_by(MinuteMeasurement.bucket_start)
                .limit(11_520)
            ).all()
            stride = max(1, (len(rows) + max_points - 1) // max_points)
            points = [
                [iso(row.bucket_start), row[1]] for row in rows[::stride] if row[1] is not None
            ]
            output.append(
                {
                    "device_id": device.id,
                    "name": device.name,
                    "color": device.color,
                    "points": points,
                }
            )
    return {
        "metric": metric,
        "phase": phase,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "series": output,
    }


@router.get("/history-batch")
def history_batch(
    request: Request,
    series: str = Query(
        default="current:l1,current:l2,current:l3",
        max_length=512,
    ),
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    max_points: int = Query(default=1440, ge=60, le=2880),
) -> dict[str, object]:
    requested = _parse_series(series)
    if not requested:
        return {"series": [], "error": "no_valid_series"}
    now = utc_now()
    try:
        end = min(now, _parse_time(to_time) if to_time else now)
        start = _parse_time(from_time) if from_time else end - timedelta(hours=24)
    except ValueError:
        return {"series": [], "error": "invalid_time"}
    start = max(start, end - timedelta(days=8))
    columns = [
        getattr(MinuteMeasurement, f"{metric}_{phase}_avg").label(f"{metric}_{phase}")
        for metric, phase in requested
    ]
    runtime = request.app.state.runtime
    output: list[dict[str, object]] = []
    with runtime.database.sessions() as session:
        enabled_devices = session.scalars(
            select(Device)
            .where(Device.enabled.is_(True), Device.removed_at.is_(None))
            .order_by(Device.sort_order, Device.name)
            .limit(200)
        ).all()
        for device in enabled_devices:
            rows = session.execute(
                select(MinuteMeasurement.bucket_start, *columns)
                .where(
                    MinuteMeasurement.device_id == device.id,
                    MinuteMeasurement.bucket_start >= start,
                    MinuteMeasurement.bucket_start <= end,
                )
                .order_by(MinuteMeasurement.bucket_start)
                .limit(11_520)
            ).all()
            stride = max(1, (len(rows) + max_points - 1) // max_points)
            sampled = rows[::stride]
            for column_index, (metric, phase) in enumerate(requested, start=1):
                points = [
                    [iso(row.bucket_start), row[column_index]]
                    for row in sampled
                    if row[column_index] is not None
                ]
                output.append(
                    {
                        "key": f"{device.id}:{metric}:{phase}",
                        "device_id": device.id,
                        "name": device.name,
                        "metric": metric,
                        "phase": phase,
                        "points": points,
                    }
                )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "aggregated": True,
        "interval": "minute",
        "series": output,
    }


@router.get("/window-stats")
def window_stats(
    request: Request,
    metric: str = Query(default="power", pattern="^(current|voltage|power)$"),
    phase: str = Query(default="total", pattern="^(l1|l2|l3|total)$"),
) -> list[dict[str, object]]:
    if phase not in VALID_SERIES[metric]:
        return []
    runtime = request.app.state.runtime
    with runtime.database.sessions() as session:
        rows = session.execute(
            select(DeviceWindowStat, Device.name)
            .join(Device, Device.id == DeviceWindowStat.device_id)
            .where(
                Device.enabled.is_(True),
                Device.removed_at.is_(None),
                DeviceWindowStat.metric == metric,
                DeviceWindowStat.phase == phase,
            )
            .order_by(Device.sort_order, DeviceWindowStat.window_type)
            .limit(600)
        ).all()
        return [
            {
                "device_id": stat.device_id,
                "name": name,
                "window": stat.window_type,
                "minimum": stat.minimum,
                "minimum_timestamp": iso(stat.minimum_timestamp),
                "maximum": stat.maximum,
                "maximum_timestamp": iso(stat.maximum_timestamp),
            }
            for stat, name in rows
        ]


@router.websocket("/live-stream")
async def live_stream(websocket: WebSocket) -> None:
    runtime = websocket.app.state.runtime
    await runtime.websockets.connect(websocket)
    try:
        await websocket.send_json(
            {
                "type": "snapshot",
                "data": [item.public_dict() for item in runtime.live_store.latest().values()],
            }
        )
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except TimeoutError:
                await websocket.send_json({"type": "ping", "server_time": utc_now().isoformat()})
    except WebSocketDisconnect:
        pass
    finally:
        await runtime.websockets.disconnect(websocket)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone is required")
    return parsed


def _parse_series(value: str) -> list[tuple[str, str]]:
    requested: list[tuple[str, str]] = []
    for item in value.split(","):
        metric, separator, phase = item.strip().partition(":")
        candidate = (metric, phase)
        if separator and phase in VALID_SERIES.get(metric, set()) and candidate not in requested:
            requested.append(candidate)
    return requested
