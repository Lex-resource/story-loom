import asyncio
from typing import Any


_background_tasks: set = set()


def spawn_background_task(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def broadcast_llm_log(agent: Any, message: str, payload: dict | None = None, response: dict | None = None) -> None:
    project_id = getattr(agent, "project_id", None)
    if not project_id:
        return
    try:
        from services.stream_manager import stream_manager
        log_data = {"source": "AI通信", "message": message}
        if payload:
            log_data["llm_payload"] = payload
        if response:
            log_data["llm_response"] = response
        spawn_background_task(stream_manager.broadcast(str(project_id), "log", log_data))
    except Exception as exc:
        print(f"[AgentBase WARN] Failed to broadcast LLM log: {exc}")


async def broadcast_prompt_token_warning(agent: Any, threshold: int) -> None:
    project_id = getattr(agent, "project_id", None)
    warning_threshold_k = threshold // 1000
    input_tokens = getattr(agent, "last_input_tokens", 0)
    message = (
        f"[警告] 当前 Prompt 输入 token 数 ({input_tokens}) 超过单次预警上限 "
        f"({warning_threshold_k}k)。这可能会导致高昂的 API 调用开销，请注意监控使用成本！"
    )
    print(f"[AgentBase WARNING] {message}")
    if not project_id:
        return
    try:
        from services.stream_manager import stream_manager
        spawn_background_task(
            stream_manager.broadcast(str(project_id), "log", {"source": "系统", "message": message})
        )
        spawn_background_task(
            stream_manager.broadcast(
                str(project_id),
                "warning",
                {
                    "chapter": getattr(agent, "current_chapter", 0),
                    "message": f"Prompt 输入 token 数 ({input_tokens}) 超过 {warning_threshold_k}k",
                },
            )
        )
    except Exception as exc:
        print(f"[AgentBase WARNING] Failed to broadcast warning: {exc}")
