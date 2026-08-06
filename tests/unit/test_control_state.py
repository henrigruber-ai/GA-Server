"""
File: tests/unit/test_control_state.py
Version: 0.3.0
Date: 2026-08-06
Purpose: Verifies pending, confirmation, conflict, timeout, and ordering semantics.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.services.control_state import ControlStateStore


def test_off_pending_on_confirmed_on() -> None:
    store = ControlStateStore()
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    store.confirm("plug", False, now)
    store.begin("plug", True, "command", now + timedelta(seconds=5))
    assert store.snapshot("plug")["pending"] is True
    transition = store.confirm("plug", True, now + timedelta(seconds=1))
    assert transition.kind == "confirmed"
    assert store.snapshot("plug")["confirmed_state"] is True
    assert store.snapshot("plug")["pending"] is False


def test_on_pending_off_confirmed_off() -> None:
    store = ControlStateStore()
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    store.confirm("plug", True, now)
    store.begin("plug", False, "command", now + timedelta(seconds=5))
    assert store.confirm("plug", False, now + timedelta(seconds=1)).kind == "confirmed"
    assert store.snapshot("plug")["confirmed_state"] is False


def test_second_command_conflict_and_timeout() -> None:
    store = ControlStateStore()
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    store.begin("plug", True, "first", now + timedelta(seconds=5))
    with pytest.raises(RuntimeError, match="command_pending"):
        store.begin("plug", False, "second", now + timedelta(seconds=5))
    conflict = store.confirm("plug", False, now + timedelta(seconds=1))
    assert conflict.kind == "conflict"
    assert store.snapshot("plug")["last_error"] == "confirmation_conflict"

    store.begin("plug", True, "third", now + timedelta(seconds=2))
    assert store.timeout("plug", "third", now + timedelta(seconds=1)) is None
    assert store.timeout("plug", "third", now + timedelta(seconds=3)) is not None
    assert store.snapshot("plug")["confirmed_state"] is False
    assert store.snapshot("plug")["last_error"] == "confirmation_timeout"


def test_newer_lwt_offline_wins_over_delayed_sensor_and_power() -> None:
    store = ControlStateStore()
    now = datetime(2026, 8, 6, 12, tzinfo=UTC)
    assert store.mark_online("plug", False, now, source="lwt")
    assert not store.mark_online(
        "plug",
        True,
        now - timedelta(seconds=1),
        source="sensor",
    )
    store.confirm("plug", True, now - timedelta(seconds=1))
    assert store.snapshot("plug")["online"] is False
