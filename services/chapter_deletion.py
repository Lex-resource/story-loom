import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import (
    Chapter,
    ChapterOutline,
    Job,
    LivingDocVersion,
    RawIssue,
    TokenUsage,
    VectorOutbox,
)
from services.novel_constants import JOB_TYPE_GENERATE
from services.project_stats import sum_project_chars


def _project_id_column(model_class):
    if hasattr(model_class, "project_id"):
        return model_class.project_id
    if hasattr(model_class, "novel_id"):
        return model_class.novel_id
    raise AttributeError(f"{model_class.__name__} has no project_id or novel_id column")


async def _delete_and_renumber(
    db: AsyncSession,
    model_class,
    pid: uuid.UUID,
    chapter_index: int,
) -> None:
    project_column = _project_id_column(model_class)
    await db.execute(
        delete(model_class).where(
            project_column == pid,
            model_class.chapter_index == chapter_index,
        )
    )
    await db.execute(
        update(model_class)
        .where(
            project_column == pid,
            model_class.chapter_index > chapter_index,
        )
        .values(chapter_index=model_class.chapter_index - 1)
    )


async def _renumber_after_deletion(
    db: AsyncSession,
    model_class,
    pid: uuid.UUID,
    chapter_index: int,
) -> None:
    project_column = _project_id_column(model_class)
    await db.execute(
        update(model_class)
        .where(
            project_column == pid,
            model_class.chapter_index > chapter_index,
        )
        .values(chapter_index=model_class.chapter_index - 1)
    )


async def delete_related_chapter_rows(
    db: AsyncSession,
    pid: uuid.UUID,
    chapter_index: int,
) -> None:
    for model_class in (
        ChapterOutline,
        LivingDocVersion,
        RawIssue,
        TokenUsage,
        VectorOutbox,
    ):
        await _delete_and_renumber(db, model_class, pid, chapter_index)


async def renumber_chapters_after_deletion(
    db: AsyncSession,
    pid: uuid.UUID,
    chapter_index: int,
) -> None:
    await _renumber_after_deletion(db, Chapter, pid, chapter_index)


async def update_novel_stats_after_delete(
    db: AsyncSession,
    pid: uuid.UUID,
    novel,
) -> int:
    count_res = await db.execute(
        select(func.count()).select_from(Chapter).where(Chapter.novel_id == pid)
    )
    written_count = int(count_res.scalar() or 0)
    novel.current_chapter = written_count
    novel.total_chapters = written_count
    novel.total_chars = await sum_project_chars(db, pid)

    job_res = await db.execute(
        select(Job)
        .where(Job.project_id == pid, Job.type == JOB_TYPE_GENERATE)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    job = job_res.scalar_one_or_none()
    if job and job.current_chapter and job.current_chapter > max(written_count, 1):
        job.current_chapter = max(written_count, 1)
    return written_count
