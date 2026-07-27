import time
from typing import Any, Callable


def reset_call_metrics(agent: Any, system_prompt: str, user_prompt: str, count_tokens: Callable[[str], int]) -> float:
    start_time = time.time()
    agent.last_duration = 0.0
    agent.last_input_tokens = count_tokens(system_prompt) + count_tokens(user_prompt)
    agent.last_output_tokens = 0
    agent.last_cache_hit_tokens = 0
    agent.last_cache_miss_tokens = 0
    return start_time


def apply_api_usage(agent: Any, api_usage: dict | None, response_text: str, count_tokens: Callable[[str], int]) -> None:
    if api_usage:
        agent.last_input_tokens = api_usage.get("prompt_tokens", agent.last_input_tokens)
        agent.last_output_tokens = api_usage.get("completion_tokens", count_tokens(response_text))
        agent.last_cache_hit_tokens = api_usage.get("prompt_cache_hit_tokens", 0)
        agent.last_cache_miss_tokens = api_usage.get("prompt_cache_miss_tokens", 0)
    else:
        agent.last_output_tokens = count_tokens(response_text)


def finalize_call_metrics(agent: Any, current_model: str, response_text: str, start_time: float, *, is_stream: bool) -> tuple[str, dict]:
    agent.last_duration = time.time() - start_time
    label = "流式请求完成" if is_stream else "请求完成"
    message = f"{current_model} {label} (耗时: {agent.last_duration:.2f}s)"
    response = {
        "response": response_text,
        "tokens": {
            "input": agent.last_input_tokens,
            "output": agent.last_output_tokens,
            "cache_hit": getattr(agent, "last_cache_hit_tokens", 0),
        },
        "latency_ms": int(agent.last_duration * 1000),
    }
    return message, response
