import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from agents.base import LLMJSONParsingError
from database import async_session
from models.novel import Chapter, Job
from services.novel_constants import (
    REVIEW_FLAG_SEVERITY_WARNING,
    REVIEW_FLAG_TYPE_FORCE_CORRECTED,
)
from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_transitions import publish_chapter_state
from services.pipeline_types import ChapterStatus, JobStatus, PipelineStep
from services.novel_constants import JOB_TYPE_POST_PROCESSING
from services.project_stats import chapter_chars_from_row, sum_project_chars

logger = logging.getLogger(__name__)


def mark_chapter_force_published(chapter) -> None:
    chapter.status = ChapterStatus.POST_PROCESSING
    set_chapter_pipeline_step(chapter, PipelineStep.EXTRACTING)
    chapter.content = chapter.edited_content or chapter.draft_content
    chapter.force_corrected = True

    flags = chapter.review_flags or []
    if not isinstance(flags, list):
        flags = []
    flag_entry = {
        "type": REVIEW_FLAG_TYPE_FORCE_CORRECTED,
        "detail": "用户手动强制发布本章节",
        "severity": REVIEW_FLAG_SEVERITY_WARNING,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not any(f.get("type") == REVIEW_FLAG_TYPE_FORCE_CORRECTED for f in flags):
        chapter.review_flags = list(flags) + [flag_entry]


def has_extractor_high_risk_review(chapter) -> bool:
    flags = chapter.review_flags or []
    if not isinstance(flags, list):
        return False
    return any(flag.get("type") == "extractor_high_risk" for flag in flags if isinstance(flag, dict))


async def publish_reviewed_extractor_chapter(db, novel, chapter) -> None:
    chapter.content = chapter.content or chapter.edited_content or chapter.draft_content
    publish_chapter_state(chapter)
    chapter.error = None
    chapter.word_count = chapter_chars_from_row(chapter)
    novel.current_chapter = max(novel.current_chapter or 0, chapter.chapter_index)
    if (novel.total_chapters or 0) < chapter.chapter_index:
        novel.total_chapters = chapter.chapter_index
    novel.total_chars = await sum_project_chars(db, novel.id)


async def _rollback_post_processing_json_error(project_id: uuid.UUID, chapter_index: int, error) -> None:
    async with async_session() as bg_db:
        ch_res = await bg_db.execute(
            select(Chapter).where(
                Chapter.novel_id == project_id,
                Chapter.chapter_index == chapter_index,
            )
        )
        chapter = ch_res.scalar_one_or_none()
        if chapter:
            chapter.status = ChapterStatus.PENDING_REVIEW
            set_chapter_pipeline_step(chapter, PipelineStep.EXTRACTING)
            chapter.error = error.raw_response
            await bg_db.commit()


async def _rollback_post_processing_failure(project_id: uuid.UUID, chapter_index: int, error: Exception) -> None:
    async with async_session() as bg_db:
        ch_res = await bg_db.execute(
            select(Chapter).where(
                Chapter.novel_id == project_id,
                Chapter.chapter_index == chapter_index,
            )
        )
        chapter = ch_res.scalar_one_or_none()
        if chapter:
            chapter.status = ChapterStatus.PENDING_REVIEW
            chapter.error = str(error)[:500]
            await bg_db.commit()


async def run_post_processing_background(project_id: uuid.UUID, chapter_index: int) -> None:
    try:
        async with async_session() as bg_db:
            from services.knowledge_merger import run_post_processing

            await run_post_processing(bg_db, project_id, chapter_index)
    except LLMJSONParsingError as error:
        await _rollback_post_processing_json_error(project_id, chapter_index, error)
        logger.exception("chapter_post_processing_json_failed project_id=%s chapter_index=%s", project_id, chapter_index)
    except Exception as error:
        await _rollback_post_processing_failure(project_id, chapter_index, error)
        logger.exception("chapter_post_processing_failed project_id=%s chapter_index=%s", project_id, chapter_index)


async def enqueue_post_processing_job(
    db,
    project_id: uuid.UUID,
    chapter_index: int,
) -> Job:
    """Create the durable job used by manual chapter publication."""
    existing = (await db.execute(
        select(Job).where(
            Job.project_id == project_id,
            Job.type == JOB_TYPE_POST_PROCESSING,
            Job.current_chapter == chapter_index,
            Job.status.in_((JobStatus.PENDING, JobStatus.RUNNING)),
        ).order_by(Job.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if existing is not None:
        return existing
    job = Job(
        project_id=project_id,
        type=JOB_TYPE_POST_PROCESSING,
        status=JobStatus.PENDING,
        current_step="extractor",
        current_chapter=chapter_index,
        params={"run_extractor": True},
    )
    db.add(job)
    await db.flush()
    return job
