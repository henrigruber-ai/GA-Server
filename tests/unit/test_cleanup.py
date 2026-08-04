"""
File: tests/unit/test_cleanup.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Verifies storage threshold and critical free-space cleanup decisions.
Changes:
- 0.1.0: Initial implementation.
"""

from app.services.cleanup import StorageSnapshot, should_cleanup


def snapshot(total: int, free: int) -> StorageSnapshot:
    return StorageSnapshot(
        database_bytes=total,
        wal_bytes=0,
        shm_bytes=0,
        free_bytes=free,
        max_bytes=1000,
        cleanup_start_bytes=850,
        cleanup_target_bytes=700,
    )


def test_cleanup_starts_at_configured_threshold() -> None:
    assert should_cleanup(snapshot(849, 1000), 100) == (False, False)
    assert should_cleanup(snapshot(850, 1000), 100) == (True, False)


def test_low_free_space_forces_critical_cleanup() -> None:
    assert should_cleanup(snapshot(200, 99), 100) == (True, True)
