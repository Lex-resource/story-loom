"""S9 回归测试：embedding 调用对瞬时故障（429/5xx/网络错误）有小重试。

一次抖动不该让 outbox 条目走失败重放；4xx 参数错误仍然立即抛出。
"""
import asyncio

import httpx
import pytest

from services import vector_embeddings


@pytest.fixture(autouse=True)
def _frozen_tunables(freeze_tunables):
    freeze_tunables(embedding_max_attempts=3)
    yield


class _FlakyClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def post(self, url, headers=None, json=None, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://test/embeddings")
    response = httpx.Response(status, request=request)
    return httpx.HTTPStatusError(
        f"status {status}", request=request, response=response
    )


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        request=httpx.Request("POST", "http://test/embeddings"),
        json={"data": [], "usage": {"total_tokens": 1}},
    )


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def _instant_sleep(delay):
        return None

    monkeypatch.setattr(vector_embeddings.asyncio, "sleep", _instant_sleep)


def test_retry_on_rate_limit_then_success(monkeypatch):
    client = _FlakyClient([_status_error(429), _ok_response()])
    monkeypatch.setattr(vector_embeddings, "get_shared_client", lambda: client)

    async def scenario():
        return await vector_embeddings._post_embeddings(
            "http://test/embeddings", {}, {"model": "m", "input": ["x"]}
        )

    assert asyncio.run(scenario()).status_code == 200
    assert client.calls == 2


def test_no_retry_on_client_error(monkeypatch):
    client = _FlakyClient([_status_error(400)])
    monkeypatch.setattr(vector_embeddings, "get_shared_client", lambda: client)

    async def scenario():
        await vector_embeddings._post_embeddings("http://test/embeddings", {}, {})

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(scenario())
    assert client.calls == 1


def test_retry_exhausts_after_max_attempts(monkeypatch):
    client = _FlakyClient([_status_error(429)] * 5)
    monkeypatch.setattr(vector_embeddings, "get_shared_client", lambda: client)

    async def scenario():
        await vector_embeddings._post_embeddings("http://test/embeddings", {}, {})

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(scenario())
    assert client.calls == 3


def test_retry_on_transport_error(monkeypatch):
    request = httpx.Request("POST", "http://test/embeddings")
    client = _FlakyClient([
        httpx.ConnectError("connection refused", request=request),
        _ok_response(),
    ])
    monkeypatch.setattr(vector_embeddings, "get_shared_client", lambda: client)

    async def scenario():
        return await vector_embeddings._post_embeddings("http://test/embeddings", {}, {})

    assert asyncio.run(scenario()).status_code == 200
    assert client.calls == 2
