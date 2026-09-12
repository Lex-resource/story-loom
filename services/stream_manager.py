import asyncio
import logging
import os
from typing import Dict, Set

import httpx
from fastapi import WebSocket

from config import settings
from services.runtime_tunables_service import get_value
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

    async def deliver_local(self, project_id: str, event_type: str, data: dict) -> None:
        """本机直接投递,**仅供** /api/internal/broadcast 回调端点使用。

        外部 worker 模式下 worker 的事件经 HTTP 回投 API,回调端点必须无条件
        走本机投递(不能走 broadcast 的"再转发回 API"分支,会成环)。
        """
        await self._deliver(project_id, event_type, data)

    async def _deliver(self, project_id: str, event_type: str, data: dict):
        connections = self.get_connections(project_id)
        if not connections:
            return
        payload = {"type": event_type, **data}
        # 并发投递 + 每客户端超时：一个慢客户端只损失自己的连接，
        # 不能阻塞其他订阅者或广播调用方。
        await asyncio.gather(
            *(
                self._send_to(ws, project_id, payload)
                for ws in list(connections)
            ),
            return_exceptions=True,
        )

    async def _send_to(self, ws: WebSocket, project_id: str, payload: dict) -> None:
        # 单个客户端投递超时：一个不读 socket 的慢客户端否则会串行拖住所有订阅者，
        # 并经 llm_responses 的内联 chunk 回调反向卡住 LLM 流消费。超时即踢出。
        # 值入库(runtime_tunables),每次投递读取。
        deliver_timeout = await get_value("stream_deliver_timeout_seconds")
        try:
            await asyncio.wait_for(
                ws.send_json(payload), timeout=deliver_timeout
            )
        except asyncio.TimeoutError:
            logger.warning("stream_client_slow_kicked project_id=%s", project_id)
            self.unregister_connection(project_id, ws)
            try:
                await ws.close(code=1011)
            except Exception:
                logger.debug("degraded:stream_manager.close_on_kick", exc_info=True)
        except Exception:
            logger.info("stream_client_disconnected project_id=%s", project_id)
            self.unregister_connection(project_id, ws)

stream_manager = StreamManager()
