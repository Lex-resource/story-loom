import logging
import os
from typing import Dict, Set

import httpx
from fastapi import WebSocket

from config import settings
from services.stream_constants import (
    STREAM_FORWARD_TIMEOUT_SECONDS,
)

_IS_WORKER = os.environ.get("IS_WORKER") == "1"
_http_client: httpx.AsyncClient | None = None
logger = logging.getLogger(__name__)


async def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=STREAM_FORWARD_TIMEOUT_SECONDS, trust_env=False)
    return _http_client


async def close_stream_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


class StreamManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    def get_connections(self, project_id: str) -> Set[WebSocket]:
        if project_id not in self.active_connections:
            self.active_connections[project_id] = set()
        return self.active_connections[project_id]

    def register_connection(self, project_id: str, websocket: WebSocket):
        self.get_connections(project_id).add(websocket)

    def unregister_connection(self, project_id: str, websocket: WebSocket):
        if project_id in self.active_connections:
            self.active_connections[project_id].discard(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]

    async def broadcast(self, project_id: str, event_type: str, data: dict):
        if _IS_WORKER:
            await self._forward_to_api(project_id, event_type, data)
            return
        await self._deliver(project_id, event_type, data)

    async def _forward_to_api(self, project_id: str, event_type: str, data: dict):
        try:
            client = await _get_http_client()
            url = f"{settings.API_INTERNAL_URL.rstrip('/')}{settings.INTERNAL_BROADCAST_PATH}"
            response = await client.post(
                url,
                json={"project_id": project_id, "event_type": event_type, "data": data},
                headers={"X-Internal-Token": settings.STREAM_INTERNAL_TOKEN},
            )
            response.raise_for_status()
        except Exception:
            logger.exception("stream_forward_failed project_id=%s event_type=%s", project_id, event_type)

    async def _deliver(self, project_id: str, event_type: str, data: dict):
        connections = self.get_connections(project_id)
        if not connections:
            return
        payload = {"type": event_type, **data}
        for ws in list(connections):
            try:
                await ws.send_json(payload)
            except Exception:
                logger.info("stream_client_disconnected project_id=%s", project_id)
                self.unregister_connection(project_id, ws)

stream_manager = StreamManager()
