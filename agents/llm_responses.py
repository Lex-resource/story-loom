import asyncio
import json
from typing import Any, Optional

from agents.llm_streaming import ThinkStreamParser
from agents.prompt_utils import strip_emojis


import logging

logger = logging.getLogger(__name__)


async def consume_streaming_response(response, on_chunk: Optional[Any]) -> tuple[str, Optional[dict]]:
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        raise ValueError("API response returned HTML instead of stream")
    await _raise_stream_http_error(response)

    full_content = []
    api_usage = None
    parser = ThinkStreamParser()
    data_events = 0
    parsed_events = 0
    parse_errors: list[str] = []
    reasoning_chars = 0
    async for line in response.aiter_lines():
        if not line.strip():
            continue
        if not line.startswith("data: "):
            continue
        data_str = line[6:].strip()
        if data_str == "[DONE]":
            break
        data_events += 1
        try:
            chunk_data = json.loads(data_str)
            parsed_events += 1
            if "error" in chunk_data:
                raise ValueError(f"LLM API returned error: {chunk_data['error']}")
            normal, reasoning_len = await _consume_stream_chunk(chunk_data, parser, on_chunk)
            reasoning_chars += reasoning_len
            if normal:
                full_content.append(normal)
            if "usage" in chunk_data and chunk_data["usage"]:
                api_usage = chunk_data["usage"]
        except Exception as e:
            if "LLM API returned error" in str(e):
                raise
            parse_errors.append(f"{type(e).__name__}: {e}; raw={_preview(data_str)}")
            if len(parse_errors) <= 3:
                logger.warning(f"[LLM Stream WARN] Failed to parse stream chunk: {parse_errors[-1]}")

    normal, reasoning = parser.flush()
    await _emit_chunk(on_chunk, "reasoning", reasoning)
    reasoning_chars += len(reasoning or "")
    if normal:
        full_content.append(normal)
        await _emit_chunk(on_chunk, "llm", normal)

    res_str = strip_emojis("".join(full_content))
    if not res_str:
        detail = (
            f"data_events={data_events}, parsed_events={parsed_events}, "
            f"parse_errors={len(parse_errors)}, reasoning_chars={reasoning_chars}"
        )
        if parse_errors:
            raise ValueError(
                "LLM stream parsing produced an empty response "
                f"({detail}); first_error={parse_errors[0]}"
            )
        if reasoning_chars:
            raise ValueError(
                "LLM API returned reasoning-only stream without final content "
                f"({detail})"
            )
        raise ValueError(f"LLM API returned an empty response ({detail})")
    return res_str, api_usage


def parse_non_streaming_response(response) -> tuple[str, Optional[dict]]:
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        raise ValueError("API response returned HTML instead of JSON")
    _raise_http_error(response)
    data = response.json()
    if "error" in data:
        raise ValueError(f"LLM API returned error: {data['error']}")
    if "choices" not in data or not data["choices"]:
        raise ValueError(f"LLM API returned no choices: {data}")
    res_str = data["choices"][0]["message"]["content"]
    if not res_str:
        raise ValueError("LLM API returned an empty response")
    return strip_emojis(res_str), data.get("usage")


async def _consume_stream_chunk(
    chunk_data: dict,
    parser: ThinkStreamParser,
    on_chunk: Optional[Any],
) -> tuple[str, int]:
    collected = []
    if "choices" not in chunk_data or not chunk_data["choices"]:
        return "", 0
    choice = chunk_data["choices"][0]
    delta = choice.get("delta", {})
    message = choice.get("message", {}) if isinstance(choice.get("message"), dict) else {}
    reasoning_content = delta.get("reasoning_content", "") or message.get("reasoning_content", "")
    await _emit_chunk(on_chunk, "reasoning", reasoning_content)

    content = delta.get("content", "") or message.get("content", "") or choice.get("text", "")
    if not content:
        return "", len(reasoning_content or "")
    normal, reasoning = parser.process(strip_emojis(content))
    await _emit_chunk(on_chunk, "reasoning", reasoning)
    if normal:
        collected.append(normal)
        await _emit_chunk(on_chunk, "llm", normal)
    return "".join(collected), len(reasoning_content or "") + len(reasoning or "")


async def _emit_chunk(on_chunk: Optional[Any], channel: str, content: str) -> None:
    if not content or not on_chunk:
        return
    if asyncio.iscoroutinefunction(on_chunk):
        await on_chunk(channel, content)
    else:
        on_chunk(channel, content)


async def _raise_stream_http_error(response) -> None:
    """Expose upstream error bodies before consuming a streaming response."""
    if getattr(response, "status_code", 200) < 400:
        return
    try:
        await response.aread()
    except Exception:
        pass
    status = getattr(response, "status_code", "unknown")
    detail = _preview(getattr(response, "text", ""))
    raise ValueError(f"LLM API HTTP {status}: {detail or 'empty response'}")


def _raise_http_error(response) -> None:
    """Expose upstream error bodies for non-streaming requests."""
    if getattr(response, "status_code", 200) < 400:
        return
    status = getattr(response, "status_code", "unknown")
    detail = _preview(getattr(response, "text", ""))
    raise ValueError(f"LLM API HTTP {status}: {detail or 'empty response'}")


def _preview(value: str, limit: int = 240) -> str:
    value = value.replace("\n", "\\n").replace("\r", "\\r")
    if len(value) <= limit:
        return value
    return value[:limit] + "..."
