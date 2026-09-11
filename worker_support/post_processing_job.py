"""Durable handler for post-processing jobs created by manual publication."""

from __future__ import annotations

import asyncio

from agents.base import LLMJSONParsingError
from sqlalchemy import select

from models.novel import Chapter, Job, Novel
from services.job_payload import append_job_error
from services.knowledge_merger import run_post_processing
from services.novel_constants import JOB_TYPE_POST_PROCESSING
from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_types import ChapterStatus, JobStatus, NovelStatus, PipelineStep
from services.runtime_tunables_service import get_value


class PostProcessingJobAborted(Exception):
    """Raised when a durable post-processing job is cancelled mid-run."""


async def _load_rows(db, job):
    novel = (await db.execute(select(Novel).where(Novel.id == job.project_id))).scalar_one_or_none()
    chapter = (await db.execute(
        select(Chapter).where(
            Chapter.novel_id == job.project_id,
            Chapter.chapter_index == job.current_chapter,
        )
    )).scalar_one_or_none()
    if novel is None or chapter is None:
        raise LookupError("Post-processing project or chapter not found")
    return novel, chapter


async def _ensure_running(db, job) -> None:
    status = (await db.execute(select(Job.status).where(Job.id == job.id))).scalar_one_or_none()
    if status != JobStatus.RUNNING:
        raise PostProcessingJobAborted(str(status or JobStatus.CANCELLED))


async def _mark_recoverable_failure(db, job, *, message: str, terminal: bool) -> None:
    project_id = job.project_id
    chapter_index = job.current_chapter
    await db.rollback()
    novel = (await db.execute(select(Novel).where(Novel.id == project_id))).scalar_one_or_none()
    chapter = (await db.execute(
        select(Chapter).where(
            Chapter.novel_id == project_id,
            Chapter.chapter_index == chapter_index,
        )
    )).scalar_one_or_none()
    if novel is None or chapter is None:
        raise LookupError("Post-processing project or chapter not found")
    chapter.status = ChapterStatus.POSTPROCESS_FAILED if terminal else ChapterStatus.PENDING_REVIEW
    set_chapter_pipeline_step(chapter, PipelineStep.EXTRACTING, update_status=False)
    chapter.error = message[:1000]
    job.status = JobStatus.FAILED if terminal else JobStatus.PAUSED
    job.current_step = "extractor"
    append_job_error(job, message, chapter=chapter.chapter_index, step="extractor")
    novel.status = NovelStatus.PAUSED
    await db.commit()


async def process_post_processing_job(db, job: Job) -> None:
    if job.type != JOB_TYPE_POST_PROCESSING:
        raise ValueError("Invalid post-processing job type")
    novel, chapter = await _load_rows(db, job)
    await _ensure_running(db, job)
    try:
        timeout_seconds = max(1, int(await get_value("post_processing_timeout_seconds")))
        await asyncio.wait_for(
            run_post_processing(
                db,
                novel.id,
                chapter.chapter_index,
                run_extractor=bool((job.params or {}).get("run_extractor", True)),
                ensure_active=lambda: _ensure_running(db, job),
            ),
            timeout=timeout_seconds,
        )
    except PostProcessingJobAborted as exc:
        await db.rollback()
        job.status = str(exc) or JobStatus.CANCELLED
        return
    except asyncio.TimeoutError as exc:
        message = (
            f"第{chapter.chapter_index}章设定提取超过 {timeout_seconds} 秒未完成，"
            "正文已保留，可从提取器步骤继续。"
        )
        await _mark_recoverable_failure(db, job, message=message, terminal=True)
        raise RuntimeError(message) from exc
    except LLMJSONParsingError:
        message = f"第{chapter.chapter_index}章后处理 JSON 解析失败，已暂停等待人工复核。"
        await _mark_recoverable_failure(db, job, message=message, terminal=False)
    except Exception as exc:
        message = f"第{chapter.chapter_index}章后处理失败：{exc}"
        await _mark_recoverable_failure(db, job, message=message, terminal=True)
        raise
