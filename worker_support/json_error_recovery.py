"""Recovery policy for LLM JSON parsing failures during generation."""

from __future__ import annotations

import json
import uuid
from enum import StrEnum

from agents.base import LLMJSONParsingError
from agents.constants import AGENT_PLANNER, AGENT_WRITER
from models.novel import Job, Novel
from services.job_payload import append_job_error
from services.pipeline_transitions import (
    StateMachine,
    set_chapter_pipeline_step,
)
from services.pipeline_types import JobStatus, NovelStatus, PipelineStep
from services.project_stats import chapter_chars_from_row
from sqlalchemy.ext.asyncio import AsyncSession
from worker_support.chapter_repository import get_or_create_chapter
from worker_support.events import GenerationEvents
from services.knowledge_merger import run_post_processing


class JSONErrorRecoveryOutcome(StrEnum):
    RETRY = "retry"
    RECOVERED = "recovered"
    FAILED = "failed"


async def handle_json_parsing_error(
    db: AsyncSession,
    job: Job,
    novel: Novel,
    chapter_index: int,
    retry_count: int,
    error: LLMJSONParsingError,
    events: GenerationEvents,
) -> JSONErrorRecoveryOutcome:
    chapter = await get_or_create_chapter(
        db,
        novel.id,
        chapter_index,
        title=f"第{chapter_index}章",
    )

    append_job_error(
        job,
        f"JSON格式校验或Schema验证失败: {str(error)}",
        validation_failed_chapter=chapter_index,
    )

    if retry_count < 3:
        await _mark_retry(db, job, novel, chapter, chapter_index, retry_count, error, events)
        return JSONErrorRecoveryOutcome.RETRY

    usable_text = chapter.edited_content or chapter.draft_content or chapter.content
    if usable_text:
        # Editor 的短篇响应缺少必需评分维度（或其它 Editor schema 字段）时，
        # 正文虽然可读，但不能把它伪装成「法则审查通过」直接强制保存。先给一次
        # 有界的 Writer 重写机会，让 Editor 重新生成完整结构化结果；再次失败则
        # 标记失败并等待人工处理，而不是把 schema 错误写成 auto_force_saved。
        if _is_editor_schema_error(error):
            if retry_count == 3:
                await _schedule_editor_schema_rewrite(
                    db, job, novel, chapter, chapter_index, error, events
                )
                return JSONErrorRecoveryOutcome.RETRY
            await _fail_after_editor_schema_rewrite(
                db, job, novel, chapter, chapter_index, error, events
            )
            return JSONErrorRecoveryOutcome.FAILED
        await _force_save_usable_text(db, novel.id, chapter, chapter_index, usable_text, error)
        return JSONErrorRecoveryOutcome.RECOVERED

    await _fail_without_usable_text(db, job, novel, chapter, chapter_index, error, events)
    return JSONErrorRecoveryOutcome.FAILED


def _is_editor_schema_error(error: LLMJSONParsingError) -> bool:
    """识别 Editor 输出的结构化响应校验失败。

    ``LLMJSONParsingError`` 保留了 Pydantic 的原始 validation_error；优先使用
    schema title，字符串兜底兼容旧版 Pydantic/测试 double。普通 Planner/Writer
    JSON 错误不走这条分流，继续沿用既有恢复策略。
    """
    validation_error = getattr(error, "validation_error", None)
    title = str(getattr(validation_error, "title", "") or "")
    message = f"{error} {validation_error or ''}"
    return title.startswith("Editor") or "EditorResponse" in message


async def _schedule_editor_schema_rewrite(
    db: AsyncSession,
    job: Job,
    novel: Novel,
    chapter,
    chapter_index: int,
    error: LLMJSONParsingError,
    events: GenerationEvents,
) -> None:
    """把可用正文退回 Writer，修复 Editor schema 输出，而不是强制放行。"""
    chapter.status = "draft"
    chapter.edited_content = None
    chapter.error = json.dumps(
        {
            "auto_rewrite": True,
            "retry_count": 3,
            "raw_response": error.raw_response,
        },
        ensure_ascii=False,
    )
    set_chapter_pipeline_step(chapter, PipelineStep.WRITING)
    job.status = JobStatus.RUNNING
    job.current_chapter = chapter_index
    job.current_step = AGENT_WRITER
    novel.status = NovelStatus.GENERATING
    await db.commit()
    try:
        await events.status(
            AGENT_WRITER,
            chapter_index,
            "Editor结构化输出缺少必需字段，未强制保存；正在自动重写正文并重新审校。",
        )
    except Exception:
        pass


async def _fail_after_editor_schema_rewrite(
    db: AsyncSession,
    job: Job,
    novel: Novel,
    chapter,
    chapter_index: int,
    error: LLMJSONParsingError,
    events: GenerationEvents,
) -> None:
    """一次自动重写后仍无法得到 Editor 结构化结果时，安全停下等待人工处理。"""
    StateMachine.fail_job(job)
    novel.status = NovelStatus.PAUSED
    chapter.status = "failed"
    chapter.error = json.dumps(
        {
            "editor_schema_rewrite_failed": True,
            "raw_response": error.raw_response,
        },
        ensure_ascii=False,
    )
    await db.commit()
    try:
        await events.status(
            job.current_step,
            chapter_index,
            "Editor结构化输出在自动重写后仍不完整，未强制保存，已暂停等待人工处理。",
        )
    except Exception:
        pass


async def _mark_retry(
    db: AsyncSession,
    job: Job,
    novel: Novel,
    chapter,
    chapter_index: int,
    retry_count: int,
    error: LLMJSONParsingError,
    events: GenerationEvents,
) -> None:
    chapter.status = "draft"
    chapter.error = json.dumps(
        {
            "auto_retry": True,
            "retry_count": retry_count,
            "raw_response": error.raw_response,
        },
        ensure_ascii=False,
    )
    job.status = JobStatus.RUNNING
    job.current_chapter = chapter_index
    job.current_step = AGENT_PLANNER
    novel.status = NovelStatus.GENERATING
    await db.commit()
    try:
        await events.status(
            job.current_step,
            chapter_index,
            f"智能体输出数据验证失败，正在自动重试修复（第 {retry_count}/3 次）。",
        )
    except Exception:
        pass


async def _force_save_usable_text(
    db: AsyncSession,
    novel_id: uuid.UUID,
    chapter,
    chapter_index: int,
    usable_text: str,
    error: LLMJSONParsingError,
) -> None:
    chapter.content = usable_text
    chapter.validator_result = {
        "passed": True,
        "errors": [f"JSON格式校验或Schema验证失败: {str(error)}"],
        "warnings": [],
        "infos": [],
        "auto_force_saved": True,
    }
    chapter.error = json.dumps(
        {
            "auto_force_saved": True,
            "raw_response": error.raw_response,
        },
        ensure_ascii=False,
    )
    chapter.word_count = chapter_chars_from_row(chapter)
    set_chapter_pipeline_step(chapter, PipelineStep.VALIDATING)
    chapter.status = "validated"
    await db.commit()
    await run_post_processing(db, novel_id, chapter_index)


async def _fail_without_usable_text(
    db: AsyncSession,
    job: Job,
    novel: Novel,
    chapter,
    chapter_index: int,
    error: LLMJSONParsingError,
    events: GenerationEvents,
) -> None:
    StateMachine.fail_job(job)
    novel.status = NovelStatus.PAUSED
    chapter.status = "failed"
    chapter.error = error.raw_response
    await db.commit()
    try:
        await events.status(
            job.current_step,
            chapter_index,
            "智能体输出数据验证失败，已自动重试但没有可用正文可保存。",
        )
    except Exception:
        pass
