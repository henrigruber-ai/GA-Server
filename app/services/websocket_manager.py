"""
File: app/services/websocket_manager.py
Version: 0.1.0
Date: 2026-08-03
Purpose: Tracks public WebSocket clients and broadcasts sanitized live updates.
Changes:
- 0.1.0: Initial implementation.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from fastapi import WebSocket

LOGGER = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self._connections)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, message: dict[str, object]) -> None:
        stale: list[WebSocket] = []
        async with self._lock:
            connections = list(self._connections)
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)
        if stale:
            async with self._lock:
                for websocket in stale:
                    self._connections.discard(websocket)
            LOGGER.debug("Removed %d disconnected WebSocket clients", len(stale))

    async def close_all(self) -> None:
        async with self._lock:
            connections = list(self._connections)
            self._connections.clear()
        for websocket in connections:
            with suppress(Exception):
                await websocket.close(code=1001)
