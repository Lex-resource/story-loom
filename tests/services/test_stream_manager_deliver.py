"""S13 回归测试：慢 WebSocket 客户端被超时踢出，不拖住其他订阅者。

投递超时已入库（runtime_tunables），测试用 freeze_tunables 覆盖快照值。
"""
import asyncio
import time

import pytest

from services.runtime_tunables_service import PARAM_SPECS
from services.stream_manager import StreamManager


class _FakeWS:
    def __init__(self, name: str, delay: float = 0.0):
        self.name = name
        self.delay = delay
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, payload):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.sent.append(payload)

    async def close(self, code=None):
        self.closed = True


@pytest.fixture
def manager(freeze_tunables):
    sm = StreamManager()
    freeze_tunables(stream_deliver_timeout_seconds=0.05)
    return sm


def test_slow_client_kicked_fast_client_unaffected(manager):
    fast = _FakeWS("fast")
    slow = _FakeWS("slow", delay=10.0)
    manager.register_connection("p1", fast)
    manager.register_connection("p1", slow)

    started = time.monotonic()
    asyncio.run(manager._deliver("p1", "log", {"message": "hi"}))
    elapsed = time.monotonic() - started

    # 快客户端正常收到事件；慢客户端被踢出且整个投递远快于其 10s 的 delay
    assert fast.sent == [{"type": "log", "message": "hi"}]
    assert slow.sent == []
    assert slow.closed is True
    assert elapsed < 2.0
    connections = manager.active_connections["p1"]
    assert fast in connections
    assert slow not in connections


def test_disconnected_client_removed(manager):
    ws = _FakeWS("gone")

    async def boom(payload):
        raise RuntimeError("socket closed")

    ws.send_json = boom
    manager.register_connection("p1", ws)

    asyncio.run(manager._deliver("p1", "log", {"message": "hi"}))

    assert "p1" not in manager.active_connections or ws not in manager.active_connections["p1"]


def test_default_timeout_is_bounded():
    assert PARAM_SPECS["stream_deliver_timeout_seconds"].max <= 60
