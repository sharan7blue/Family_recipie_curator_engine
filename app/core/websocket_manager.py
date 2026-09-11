"""WebSocket manager (stub) — tracks connections in memory, pushes JSON events."""

from __future__ import annotations

from fastapi import WebSocket

from app.core.logger import logger


class WebSocketManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, job_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(job_id, []).append(ws)

    def disconnect(self, job_id: str, ws: WebSocket) -> None:
        if job_id in self._connections and ws in self._connections[job_id]:
            self._connections[job_id].remove(ws)

    async def _send(self, job_id: str, payload: dict) -> None:
        for ws in list(self._connections.get(job_id, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                self.disconnect(job_id, ws)
        logger.info(f"[WS] job={job_id} {payload}")

    async def push_job_progress(self, job_id: str, user_id: str, stage: str, pct: int, message: str) -> None:
        await self._send(job_id, {"type": "progress", "stage": stage, "pct": pct, "message": message})

    async def push_job_complete(self, job_id: str, user_id: str, recipe: dict, cart: dict, processing_time_ms: int) -> None:
        await self._send(job_id, {"type": "complete", "recipe": recipe, "cart": cart})

    async def push_job_error(self, job_id: str, user_id: str, error: str) -> None:
        await self._send(job_id, {"type": "error", "error": error})


ws_manager = WebSocketManager()
