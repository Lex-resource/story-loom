from dataclasses import dataclass
from typing import Any, Optional

import httpx

from agents.llm_payload import build_llm_payload, debug_log_payload
from agents.llm_responses import consume_streaming_response, parse_non_streaming_response


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
        payload = build_llm_payload(
            options.model,
            options.system_prompt,
            options.user_prompt,
            options.temperature,
            options.max_tokens,
            options.response_format,
        )
        debug_log_payload(
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
        endpoint = f"{options.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if options.on_chunk:
                payload["stream"] = True
                payload["stream_options"] = {"include_usage": True}
                async with client.stream("POST", endpoint, headers=headers, json=payload) as response:
                    content, usage = await consume_streaming_response(response, options.on_chunk)
                return LLMTransportResult(content=content, usage=usage, is_stream=True)

            response = await client.post(endpoint, headers=headers, json=payload)
            content, usage = parse_non_streaming_response(response)
            return LLMTransportResult(content=content, usage=usage, is_stream=False)
