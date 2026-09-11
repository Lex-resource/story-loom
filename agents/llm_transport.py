from dataclasses import dataclass
from typing import Any, Optional

import asyncio

from agents.llm_payload import build_llm_payload, debug_log_payload
from agents.llm_responses import consume_streaming_response, parse_non_streaming_response
from services.provider_testing import validate_provider_base_url
from services.shared_http import get_shared_client


@dataclass(frozen=True)
class LLMTransportResult:
    content: str
    usage: Optional[dict]
    is_stream: bool


@dataclass(frozen=True)
class LLMTransportOptions:
    model: str
    base_url: str
    api_key: str
    system_prompt: str
    user_prompt: str
    temperature: float
    max_tokens: int
    response_format: Optional[dict] = None
    on_chunk: Optional[Any] = None


class OpenAICompatibleTransport:
    def __init__(
        self,
        *,
        timeout: float,
        debug_enabled: bool,
        log_dir: str,
        payload_size_threshold: int,
    ):
        self.timeout = timeout
        self.debug_enabled = debug_enabled
        self.log_dir = log_dir
        self.payload_size_threshold = payload_size_threshold

    async def complete_chat(self, options: LLMTransportOptions) -> LLMTransportResult:
        # httpx's read timeout only limits an idle socket. A provider can keep
        # sending partial stream data forever, so enforce the same setting as
        # a wall-clock deadline around the entire request and response parse.
        return await asyncio.wait_for(
            self._complete_chat(options),
            timeout=self.timeout,
        )

    async def _complete_chat(self, options: LLMTransportOptions) -> LLMTransportResult:
        base_url = await asyncio.to_thread(validate_provider_base_url, options.base_url)
        payload = build_llm_payload(
            options.model,
            options.system_prompt,
            options.user_prompt,
            options.temperature,
            options.max_tokens,
            options.response_format,
        )
        # DEBUG 开启时每次调用（含重试）都要写整份 payload（可达几十 MB），
        # 同步写盘会冻结事件循环，下放线程池。
        await asyncio.to_thread(
            debug_log_payload,
            payload,
            options.system_prompt,
            options.user_prompt,
            options.model,
            debug_enabled=self.debug_enabled,
            log_dir=self.log_dir,
            size_threshold=self.payload_size_threshold,
        )

        headers = {
            "Authorization": f"Bearer {options.api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{base_url.rstrip('/')}/chat/completions"

        # 进程级共享 client：连接池复用，避免每次调用/重试都重做 TCP/TLS 握手。
        # 超时按请求指定（options.timeout 随 provider 配置变化）。
        client = get_shared_client()
        if options.on_chunk:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
            async with client.stream(
                "POST", endpoint, headers=headers, json=payload, timeout=self.timeout
            ) as response:
                content, usage = await consume_streaming_response(response, options.on_chunk)
            return LLMTransportResult(content=content, usage=usage, is_stream=True)

        response = await client.post(
            endpoint, headers=headers, json=payload, timeout=self.timeout
        )
        content, usage = parse_non_streaming_response(response)
        return LLMTransportResult(content=content, usage=usage, is_stream=False)
