"""
File: app/services/control_state.py
Version: 0.3.0
Date: 2026-08-06
Purpose: Stores thread-safe confirmed, online, pending, and error state for controllable devices.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import RLock

from app.core.time import as_utc


@dataclass(slots=True)
class DeviceControlState:
    confirmed_state: bool | None = None
    confirmed_at: datetime | None = None
    online: bool = False
    online_at: datetime | None = None
    last_lwt_at: datetime | None = None
    pending: bool = False
    desired_state: bool | None = None
    command_id: str | None = None
    deadline: datetime | None = None
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class ControlTransition:
    kind: str
    command_id: str | None
    desired_state: bool | None
    confirmed_state: bool | None


class ControlStateStore:
    def __init__(self) -> None:
        self._states: dict[str, DeviceControlState] = {}
        self._lock = RLock()

    def ensure(
        self,
        device_id: str,
        *,
        online: bool | None = None,
        observed_at: datetime | None = None,
    ) -> None:
        with self._lock:
            state = self._states.setdefault(device_id, DeviceControlState())
            normalized = as_utc(observed_at) if observed_at else None
            if online is not None and (
                state.online_at is None
                or (normalized is not None and normalized >= as_utc(state.online_at))
            ):
                state.online = online
                state.online_at = normalized or state.online_at

    def mark_online(
        self,
        device_id: str,
        online: bool,
        observed_at: datetime,
        *,
        source: str,
    ) -> bool:
        observed_at = as_utc(observed_at)
        with self._lock:
            state = self._states.setdefault(device_id, DeviceControlState())
            if state.online_at is not None and observed_at < as_utc(state.online_at):
                return False
            if (
                online
                and source != "lwt"
                and state.last_lwt_at is not None
                and observed_at <= as_utc(state.last_lwt_at)
                and not state.online
            ):
                return False
            if source == "lwt":
                if state.last_lwt_at is not None and observed_at < as_utc(state.last_lwt_at):
                    return False
                state.last_lwt_at = observed_at
            state.online = online
            state.online_at = observed_at
            if not online and state.pending:
                state.last_error = "device_offline"
            return True

    def begin(
        self,
        device_id: str,
        desired_state: bool,
        command_id: str,
        deadline: datetime,
    ) -> DeviceControlState:
        with self._lock:
            state = self._states.setdefault(device_id, DeviceControlState())
            if state.pending:
                raise RuntimeError("command_pending")
            state.pending = True
            state.desired_state = desired_state
            state.command_id = command_id
            state.deadline = as_utc(deadline)
            state.last_error = None
            return self._copy(state)

    def reject(self, device_id: str, command_id: str, error: str) -> ControlTransition | None:
        with self._lock:
            state = self._states.setdefault(device_id, DeviceControlState())
            if not state.pending or state.command_id != command_id:
                return None
            transition = ControlTransition(
                "rejected",
                state.command_id,
                state.desired_state,
                state.confirmed_state,
            )
            self._clear_pending(state)
            state.last_error = error
            return transition

    def confirm(
        self,
        device_id: str,
        confirmed_state: bool,
        observed_at: datetime,
    ) -> ControlTransition:
        observed_at = as_utc(observed_at)
        with self._lock:
            state = self._states.setdefault(device_id, DeviceControlState())
            if state.confirmed_at is not None and observed_at < as_utc(state.confirmed_at):
                return ControlTransition(
                    "stale",
                    state.command_id,
                    state.desired_state,
                    state.confirmed_state,
                )
            command_id = state.command_id
            desired_state = state.desired_state
            kind = "observed"
            if state.pending:
                kind = "confirmed" if desired_state is confirmed_state else "conflict"
                self._clear_pending(state)
            state.confirmed_state = confirmed_state
            state.confirmed_at = observed_at
            if state.last_lwt_at is None or observed_at > as_utc(state.last_lwt_at) or state.online:
                state.online = True
                state.online_at = observed_at
            state.last_error = "confirmation_conflict" if kind == "conflict" else None
            return ControlTransition(kind, command_id, desired_state, confirmed_state)

    def timeout(
        self,
        device_id: str,
        command_id: str,
        now: datetime,
    ) -> ControlTransition | None:
        now = as_utc(now)
        with self._lock:
            state = self._states.setdefault(device_id, DeviceControlState())
            if (
                not state.pending
                or state.command_id != command_id
                or state.deadline is None
                or now < as_utc(state.deadline)
            ):
                return None
            transition = ControlTransition(
                "timeout",
                state.command_id,
                state.desired_state,
                state.confirmed_state,
            )
            self._clear_pending(state)
            state.last_error = "confirmation_timeout"
            return transition

    def snapshot(self, device_id: str) -> dict[str, object]:
        with self._lock:
            state = self._states.setdefault(device_id, DeviceControlState())
            return self._snapshot(state)

    def all_snapshots(self) -> dict[str, dict[str, object]]:
        with self._lock:
            return {device_id: self._snapshot(state) for device_id, state in self._states.items()}

    @staticmethod
    def _clear_pending(state: DeviceControlState) -> None:
        state.pending = False
        state.desired_state = None
        state.command_id = None
        state.deadline = None

    @staticmethod
    def _copy(state: DeviceControlState) -> DeviceControlState:
        return DeviceControlState(
            confirmed_state=state.confirmed_state,
            confirmed_at=state.confirmed_at,
            online=state.online,
            online_at=state.online_at,
            last_lwt_at=state.last_lwt_at,
            pending=state.pending,
            desired_state=state.desired_state,
            command_id=state.command_id,
            deadline=state.deadline,
            last_error=state.last_error,
        )

    @staticmethod
    def _snapshot(state: DeviceControlState) -> dict[str, object]:
        return {
            "confirmed_state": state.confirmed_state,
            "confirmed_at": state.confirmed_at.isoformat() if state.confirmed_at else None,
            "online": state.online,
            "online_at": state.online_at.isoformat() if state.online_at else None,
            "pending": state.pending,
            "desired_state": state.desired_state,
            "command_id": state.command_id,
            "deadline": state.deadline.isoformat() if state.deadline else None,
            "last_error": state.last_error,
        }
