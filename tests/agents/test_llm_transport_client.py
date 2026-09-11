"""S8 回归测试：LLM transport 复用共享 client，超时按请求传递。"""
import asyncio

import httpx
import pytest

pytest.importorskip("fastapi")

from agents.llm_transport import LLMTransportOptions, OpenAICompatibleTransport


class _RecordingClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )


def _make_options() -> LLMTransportOptions:
    return LLMTransportOptions(
        model="test-model",
        base_url="http://llm",
        api_key="key",
        system_prompt="sys",
        user_prompt="user",
        temperature=0.1,
        max_tokens=8,
    )


def test_transport_uses_shared_client_and_per_request_timeout(monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr("agents.llm_transport.get_shared_client", lambda: client)
    monkeypatch.setattr(
        "agents.llm_transport.validate_provider_base_url",
        lambda base_url: base_url,
    )

    transport = OpenAICompatibleTransport(
        timeout=7, debug_enabled=False, log_dir="logs", payload_size_threshold=1000
    )

    result = asyncio.run(transport._complete_chat(_make_options()))

    assert result.content == "ok"
    assert client.calls[0]["timeout"] == 7
    assert client.calls[0]["url"] == "http://llm/chat/completions"

    # 二次调用仍复用同一 client 实例（不重建连接池）
    asyncio.run(transport._complete_chat(_make_options()))
    assert len(client.calls) == 2
