import asyncio
import logging
from typing import Any

from services.runtime_tunables_service import get_value_sync

logger = logging.getLogger(__name__)

_background_tasks: set = set()


def _truncate_for_log(value: str) -> str:
    """广播日志里 prompt/response 正文的截断。上限入库(runtime_tunables)。

    前端「检查」面板会展示这些字段,所以阈值放宽到 16K 字符;不截断的话
    多 MB 的事件会拖慢 WS 投递并占满内存。同步读点:读进程内快照。
    """
    limit = get_value_sync("log_text_char_limit")
    if len(value) <= limit:
        return value
    return value[:limit] + f"…[已截断，原文共 {len(value)} 字符]"


def _slim_log_value(value):
    """递归瘦身：嵌套 dict/list 里的长字符串也要截断，否则漏网。"""
    if isinstance(value, str):
        return _truncate_for_log(value)
    if isinstance(value, dict):
        return {key: _slim_log_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_slim_log_value(item) for item in value]
    return value


def _slim_log_dict(data: dict) -> dict:
    return _slim_log_value(data)


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
            log_data["llm_payload"] = _slim_log_dict(payload)
        if response:
            log_data["llm_response"] = _slim_log_dict(response)
        spawn_background_task(stream_manager.broadcast(str(project_id), "log", log_data))
    except Exception:
        logger.exception("llm_log_broadcast_failed project_id=%s", project_id)


async def broadcast_prompt_token_warning(agent: Any, threshold: int) -> None:
    project_id = getattr(agent, "project_id", None)
    warning_threshold_k = threshold // 1000
    input_tokens = getattr(agent, "last_input_tokens", 0)
    message = (
        f"[警告] 当前 Prompt 输入 token 数 ({input_tokens}) 超过单次预警上限 "
        f"({warning_threshold_k}k)。这可能会导致高昂的 API 调用开销，请注意监控使用成本！"
    )
    logger.warning("prompt_token_threshold_exceeded tokens=%s threshold_k=%sk", input_tokens, warning_threshold_k)
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
    except Exception:
        logger.exception("prompt_warning_broadcast_failed project_id=%s", project_id)
