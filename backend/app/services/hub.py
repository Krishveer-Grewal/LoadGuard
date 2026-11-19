"""WebSocket fan-out. Worker threads publish; the asyncio loop delivers to clients."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import WebSocket

log = logging.getLogger("loadguard.hub")


class Hub:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def bind(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def _send_all(self, text: str):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def publish(self, msg: dict[str, Any]):
        """Thread-safe publish from worker threads."""
        if self.loop is None or not self.clients:
            return
        text = json.dumps(msg, default=str)
        try:
            asyncio.run_coroutine_threadsafe(self._send_all(text), self.loop)
        except RuntimeError:
            pass


hub = Hub()
