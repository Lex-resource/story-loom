"""Recovery policy for LLM JSON parsing failures during generation."""

from __future__ import annotations

import json
import uuid
from enum import StrEnum

from agents.base import LLMJSONParsingError
from agents.constants import AGENT_PLANNER
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
        await _force_save_usable_text(db, novel.id, chapter, chapter_index, usable_text, error)
        return JSONErrorRecoveryOutcome.RECOVERED

    await _fail_without_usable_text(db, job, novel, chapter, chapter_index, error, events)
    return JSONErrorRecoveryOutcome.FAILED


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
