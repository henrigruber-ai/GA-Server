"""
File: app/runtime.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Owns application services and their coordinated startup and shutdown.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.auth.security import AuthService
from app.config import Settings
from app.core.time import utc_now
from app.db.database import Database
from app.db.seed import seed_example_devices
from app.services.aggregation import MinuteAggregator
from app.services.cleanup import CleanupService
from app.services.live_store import LiveStore
from app.services.measurement_store import MeasurementStore
from app.services.mqtt_service import MqttService
from app.services.websocket_manager import WebSocketManager

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Runtime:
    settings: Settings
    project_root: Path
    database: Database
    live_store: LiveStore
    measurement_store: MeasurementStore
    aggregator: MinuteAggregator
    websockets: WebSocketManager
    auth: AuthService
    cleanup: CleanupService
    mqtt: MqttService
    started_at: datetime
    maintenance_task: asyncio.Task[None] | None = None

    @classmethod
    def build(cls, settings: Settings, project_root: Path) -> Runtime:
        database = Database(settings.database_url)
        live_store = LiveStore(
            max_samples=settings.live_buffer_max_samples,
            max_minutes=settings.live_buffer_minutes,
        )
        measurement_store = MeasurementStore(database)
        aggregator = MinuteAggregator(measurement_store.save)
        websockets = WebSocketManager()
        return cls(
            settings=settings,
            project_root=project_root,
            database=database,
            live_store=live_store,
            measurement_store=measurement_store,
            aggregator=aggregator,
            websockets=websockets,
            auth=AuthService(database, settings),
            cleanup=CleanupService(database, settings),
            mqtt=MqttService(database, settings, live_store, aggregator, websockets),
            started_at=utc_now(),
        )

    async def start(self) -> None:
        self.database.initialize()
        if self.settings.seed_example_devices:
            with self.database.sessions() as session:
                seed_example_devices(session)
        self.mqtt.start(asyncio.get_running_loop())
        self.maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def stop(self) -> None:
        if self.maintenance_task:
            self.maintenance_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.maintenance_task
        self.mqtt.stop()
        await self.websockets.close_all()
        self.database.dispose()

    async def _maintenance_loop(self) -> None:
        cleanup_counter = 0
        while True:
            await asyncio.sleep(15)
            self.aggregator.flush_due()
            cleanup_counter += 1
            if cleanup_counter >= 20:
                cleanup_counter = 0
                try:
                    await asyncio.to_thread(self.cleanup.run_if_needed)
                except Exception:
                    LOGGER.exception("Scheduled storage maintenance failed")
