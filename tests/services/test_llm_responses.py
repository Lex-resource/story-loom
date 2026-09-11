import asyncio

import httpx
import pytest

from agents.llm_responses import consume_streaming_response, parse_non_streaming_response


def _error_response() -> httpx.Response:
    return httpx.Response(
        400,
        headers={"content-type": "application/json"},
        content=b'{"error":{"message":"Upstream request failed"}}',
        request=httpx.Request("POST", "https://provider.test/v1/chat/completions"),
    )


def test_non_streaming_error_includes_upstream_body():
    with pytest.raises(ValueError, match=r"LLM API HTTP 400.*Upstream request failed"):
        parse_non_streaming_response(_error_response())


def test_streaming_error_includes_upstream_body():
    with pytest.raises(ValueError, match=r"LLM API HTTP 400.*Upstream request failed"):
        asyncio.run(consume_streaming_response(_error_response(), None))
