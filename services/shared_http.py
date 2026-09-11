"""进程级共享的 httpx.AsyncClient。

LLM 调用（含每次重试）与 embedding 调用过去每次都新建 client，重复做
TCP/TLS 握手且连接池无法复用。这里提供进程级单例；超时由每次请求单独
指定（不同调用方的超时不同）。

注意：trust_env 保持默认 True——llm_transport 的原行为尊重环境代理变量。
不要照搬 stream_manager 的 trust_env=False（那是 localhost 内部转发专用）。

关闭时机：FastAPI lifespan shutdown 与 worker 退出时调用 close_shared_client()；
关闭后再次 get_shared_client() 会重建（uvicorn --reload 的生命周期边界）。
"""
from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None


def get_shared_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient()
    return _client


async def close_shared_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
