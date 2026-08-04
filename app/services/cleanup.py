"""
File: app/services/cleanup.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Enforces a configurable SQLite footprint by deleting oldest measurements in batches.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, func, select, text

from app.config import Settings
from app.core.time import utc_now
from app.db.database import Database
from app.db.models import AuditLog, MinuteMeasurement

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StorageSnapshot:
    database_bytes: int
    wal_bytes: int
    shm_bytes: int
    free_bytes: int
    max_bytes: int
    cleanup_start_bytes: int
    cleanup_target_bytes: int

    @property
    def total_bytes(self) -> int:
        return self.database_bytes + self.wal_bytes + self.shm_bytes

    @property
    def used_percent(self) -> float:
        return self.total_bytes / self.max_bytes * 100 if self.max_bytes else 0


def should_cleanup(snapshot: StorageSnapshot, minimum_free_bytes: int) -> tuple[bool, bool]:
    critical_disk = snapshot.free_bytes < minimum_free_bytes
    return snapshot.total_bytes >= snapshot.cleanup_start_bytes or critical_disk, critical_disk


class CleanupService:
    def __init__(self, database: Database, settings: Settings, batch_size: int = 5000) -> None:
        self.database = database
        self.settings = settings
        self.batch_size = batch_size
        self.last_result: dict[str, object] | None = None

    def snapshot(self) -> StorageSnapshot:
        path = self.settings.database_path
        if path is None:
            return StorageSnapshot(0, 0, 0, 0, 0, 0, 0)
        max_bytes = self.settings.db_max_mb * 1024 * 1024
        free = shutil.disk_usage(path.parent if path.parent.exists() else Path.cwd()).free
        return StorageSnapshot(
            database_bytes=self._size(path),
            wal_bytes=self._size(Path(f"{path}-wal")),
            shm_bytes=self._size(Path(f"{path}-shm")),
            free_bytes=free,
            max_bytes=max_bytes,
            cleanup_start_bytes=max_bytes * self.settings.cleanup_start_percent // 100,
            cleanup_target_bytes=max_bytes * self.settings.cleanup_target_percent // 100,
        )

    @staticmethod
    def _size(path: Path) -> int:
        return path.stat().st_size if path.exists() else 0

    def run_if_needed(self, *, force: bool = False) -> dict[str, object]:
        before = self.snapshot()
        needed, critical = should_cleanup(before, self.settings.min_free_disk_mb * 1024 * 1024)
        if not (needed or force):
            self.last_result = {"status": "not_needed", "before": asdict(before), "deleted": 0}
            return self.last_result
        cutoff = utc_now() - timedelta(days=self.settings.min_history_days)
        deleted_rows = 0
        while True:
            snapshot = self.snapshot()
            if not force and snapshot.total_bytes <= snapshot.cleanup_target_bytes and not critical:
                break
            with self.database.sessions.begin() as session:
                query = (
                    select(MinuteMeasurement.id)
                    .order_by(MinuteMeasurement.bucket_start.asc())
                    .limit(self.batch_size)
                )
                if not critical:
                    query = query.where(MinuteMeasurement.bucket_start < cutoff)
                ids = list(session.scalars(query))
                if not ids:
                    break
                result = session.execute(
                    delete(MinuteMeasurement).where(MinuteMeasurement.id.in_(ids))
                )
                deleted_rows += int(getattr(result, "rowcount", 0) or 0)
            if force:
                break
        with self.database.engine.begin() as connection:
            connection.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
            connection.execute(text("PRAGMA incremental_vacuum(2000)"))
        after = self.snapshot()
        status = "critical_cleanup" if critical else "cleaned"
        self.last_result = {
            "status": status,
            "before": asdict(before),
            "after": asdict(after),
            "deleted": deleted_rows,
        }
        with self.database.sessions.begin() as session:
            session.add(
                AuditLog(
                    action="storage.cleanup",
                    target_type="database",
                    details=f"status={status}; deleted={deleted_rows}",
                    severity="warning" if critical else "info",
                )
            )
        LOGGER.warning("Database cleanup complete: %s", self.last_result)
        return self.last_result

    def status(self) -> dict[str, object]:
        snapshot = self.snapshot()
        with self.database.sessions() as session:
            count = session.scalar(select(func.count()).select_from(MinuteMeasurement)) or 0
            oldest = session.scalar(select(func.min(MinuteMeasurement.bucket_start)))
            newest = session.scalar(select(func.max(MinuteMeasurement.bucket_start)))
        return {
            "storage": asdict(snapshot) | {"total_bytes": snapshot.total_bytes},
            "measurement_rows": count,
            "oldest": oldest.isoformat() if oldest else None,
            "newest": newest.isoformat() if newest else None,
            "last_cleanup": self.last_result,
            "backup_retention_days": 14,
        }
