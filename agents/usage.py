from datetime import datetime, timezone
from typing import Any, Optional

import logging
from models.novel import Chapter
from sqlalchemy import select
from database import async_session
from models.novel import TokenUsage
from database import async_session

logger = logging.getLogger(__name__)

def agent_usage_payload(agent, project_id: Any, chapter_index: int, agent_name: str) -> Optional[dict]:
    if not (hasattr(agent, "last_input_tokens") and hasattr(agent, "last_output_tokens")):
        return None
    return {
        "project_id": project_id,
        "chapter_index": chapter_index,
        "agent_name": agent_name,
        "input_tokens": getattr(agent, "last_input_tokens", 0),
        "output_tokens": getattr(agent, "last_output_tokens", 0),
        "cache_hit_tokens": getattr(agent, "last_cache_hit_tokens", 0),
        "cache_miss_tokens": getattr(agent, "last_cache_miss_tokens", 0),
        "duration": getattr(agent, "last_duration", 0.0),
        "model_name": getattr(agent, "last_model_name", None) or getattr(agent, "model", None),
    }

async def record_agent_usage(agent, project_id: Any, chapter_index: int, agent_name: str) -> None:
    payload = agent_usage_payload(agent, project_id, chapter_index, agent_name)
    if payload is None:
        return
    usage = TokenUsage(**payload)
    try:
        async with async_session() as usage_db:
            usage_db.add(usage)
            await usage_db.commit()
    except Exception as exc:
        logger.warning(f"[TokenUsage WARN] Failed to record usage for {agent_name}: {exc}")

def backup_model_flag(backup_model: str, failure_reason: str | None = None) -> dict:
    detail = f"主模型调用失败，已自动降级至备用模型 ({backup_model}) 生成内容，文风可能与主模型略有差异"
    if failure_reason:
        detail += f"；失败原因：{failure_reason[:300]}"
    return {
        "type": "backup_model",
        "detail": detail,
        "severity": "info",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

async def record_backup_model_flag(project_id, chapter_index: int, backup_model: str, failure_reason: str | None = None) -> None:
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Chapter).where(
                    Chapter.novel_id == project_id,
                    Chapter.chapter_index == chapter_index,
                )
            )
            chapter = result.scalar_one_or_none()
            if not chapter:
                return
            flags = chapter.review_flags or []
            if not isinstance(flags, list):
                flags = []
            if any(flag.get("type") == "backup_model" for flag in flags):
                return
            chapter.review_flags = list(flags) + [backup_model_flag(backup_model, failure_reason)]
            await db.commit()
            logger.info(f"[AgentBase] Recorded backup_model flag for chapter {chapter_index}.")
    except Exception as exc:
        logger.error(f"[AgentBase ERROR] Failed to record backup_model flag: {exc}")
