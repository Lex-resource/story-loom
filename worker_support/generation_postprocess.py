"""Post-processing entry flow for generated chapters."""

from __future__ import annotations

import asyncio
import logging

from agents.constants import AGENT_EXTRACTOR
from services.job_payload import append_job_error
from services.pipeline_transitions import set_chapter_pipeline_step, set_job_step
from services.pipeline_types import ChapterStatus, NovelStatus, PipelineStep
from services.runtime_tunables_service import get_value
from sqlalchemy.ext.asyncio import AsyncSession
from worker_support.events import GenerationEvents
from services.knowledge_merger import run_post_processing
from core.pipeline_vocab import ChapterStatus, JobStatus

logger = logging.getLogger(__name__)


class PostProcessingTimeoutError(TimeoutError):
    """Raised when chapter extraction exceeds its wall-clock budget."""


async def run_chapter_post_processing(
    db: AsyncSession,
    job,
    novel,
    chapter,
    chapter_index: int,
    *,
    has_extractor: bool,
    check_paused,
    events: GenerationEvents,
) -> None:
    await check_paused(db, job.id)
    chapter.status = ChapterStatus.POST_PROCESSING
    set_chapter_pipeline_step(chapter, PipelineStep.EXTRACTING)
    await db.commit()

    run_extractor = has_extractor
    if run_extractor:
        await check_paused(db, job.id)
        set_job_step(job, "extractor", chapter)
        await db.commit()
        await events.status(AGENT_EXTRACTOR, chapter_index, "正在提取世界观、人物及剧情设定更新...")
    else:
        await events.status("post_processing", chapter_index, "正在执行章节发布后处理...")

    if not run_extractor:
        await run_post_processing(db, novel.id, chapter_index, run_extractor=False)
    else:
        # 后处理超时入库(runtime_tunables),每章调用时读取。
        timeout_seconds = max(1, int(await get_value("post_processing_timeout_seconds")))
        logger.info(
            "chapter_post_processing_started project_id=%s chapter_index=%s timeout_seconds=%s",
            novel.id,
            chapter_index,
            timeout_seconds,
        )
        try:
            await asyncio.wait_for(
                run_post_processing(db, novel.id, chapter_index, run_extractor=True),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError as error:
            message = (
                f"第{chapter_index}章设定提取超过 {timeout_seconds} 秒未完成，"
                "已停止本次后处理。正文已保留，可从提取器步骤继续。"
            )
            # Cancellation may interrupt an uncommitted extractor transaction.
            # Roll it back before writing the durable recovery state.
            await db.rollback()
            chapter.status = ChapterStatus.POSTPROCESS_FAILED
            set_chapter_pipeline_step(chapter, PipelineStep.EXTRACTING, update_status=False)
            chapter.error = message
            job.status = JobStatus.FAILED
            job.current_step = AGENT_EXTRACTOR
            append_job_error(job, message, chapter=chapter_index, step=AGENT_EXTRACTOR)
            novel.status = NovelStatus.PAUSED
            await db.commit()
            try:
                await events.error(message)
            except Exception:
                logger.exception(
                    "chapter_post_processing_timeout_event_failed project_id=%s chapter_index=%s",
                    novel.id,
                    chapter_index,
                )
            logger.error(
                "chapter_post_processing_timeout project_id=%s chapter_index=%s timeout_seconds=%s",
                novel.id,
                chapter_index,
                timeout_seconds,
            )
            raise PostProcessingTimeoutError(message) from error

    await db.refresh(chapter)
    if chapter.status == ChapterStatus.PENDING_REVIEW:
        novel.status = NovelStatus.PAUSED
        job.status = JobStatus.PAUSED
        job.current_step = "extractor"
        await db.commit()
        await events.status(
            AGENT_EXTRACTOR,
            chapter_index,
            "设定变更未能自动复核，已暂停等待处理。",
        )
