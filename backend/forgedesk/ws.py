"""WebSocket fan-out. Subscribers register per project; publishing never blocks on a slow client."""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self._subs: dict[int, set[WebSocket]] = {}

    async def connect(self, project_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._subs.setdefault(project_id, set()).add(ws)

    def disconnect(self, project_id: int, ws: WebSocket) -> None:
        self._subs.get(project_id, set()).discard(ws)

    async def publish(self, project_id: int, type_: str, data: dict[str, Any]) -> None:
        message = {"type": type_, "project_id": project_id, "data": data}
        for ws in list(self._subs.get(project_id, ())):
            try:
                await asyncio.wait_for(ws.send_json(message), timeout=2)
            except Exception:
                self.disconnect(project_id, ws)
                with contextlib.suppress(Exception):
                    await ws.close()


hub = Hub()
