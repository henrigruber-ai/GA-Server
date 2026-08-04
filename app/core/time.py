"""
File: app/core/time.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Provides consistent timezone-aware UTC helpers.
Changes:
- 0.1.0: Initial implementation.
"""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def minute_bucket(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).replace(second=0, microsecond=0)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
