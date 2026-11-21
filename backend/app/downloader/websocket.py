"""Manajer koneksi WebSocket untuk monitoring batch secara real-time."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

log = logging.getLogger("app.downloader.ws")


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[Any]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, batch_id: str, websocket: Any) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[batch_id].add(websocket)

    async def disconnect(self, batch_id: str, websocket: Any) -> None:
        async with self._lock:
            conns = self._connections.get(batch_id)
            if conns:
                conns.discard(websocket)
                if not conns:
                    self._connections.pop(batch_id, None)

    def count(self, batch_id: str) -> int:
        return len(self._connections.get(batch_id, ()))

    async def broadcast(self, batch_id: str, message: dict) -> None:
        conns = list(self._connections.get(batch_id, ()))
        if not conns:
            return
        payload = json.dumps(message, ensure_ascii=False, default=str)
        dead = []
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(batch_id, ws)


manager = ConnectionManager()
