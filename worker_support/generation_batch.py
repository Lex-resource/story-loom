"""Batch-generation helpers for the generation runner."""

from __future__ import annotations

from models.novel import Chapter, Job, Novel
from services.chapter_progress import all_target_chapters_published, find_next_writable_chapter
from services.job_payload import get_job_params, set_job_params
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.pipeline_vocab import NovelStatus


async def find_next_chapter_for_job(
    db: AsyncSession,
    job: Job,
    novel: Novel,
    *,
    is_first_iteration: bool,
) -> int:
    if is_first_iteration and job.current_chapter and job.current_chapter > 0:
        return job.current_chapter

    ch_res = await db.execute(
        select(Chapter.chapter_index, Chapter.status)
        .where(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_index)
    )
    return find_next_writable_chapter(ch_res.all(), novel.target_chapters)


async def get_novel_for_job(db: AsyncSession, job: Job) -> Novel | None:
    result = await db.execute(select(Novel).where(Novel.id == job.project_id))
    return result.scalar_one_or_none()


def set_agent_chapter(agent_nodes: list, chapter_index: int) -> None:
    for agent in agent_nodes:
        agent.agent.current_chapter = chapter_index


def batch_size_from_params(job_params: dict) -> int:
    return job_params.get("remaining_chapters", job_params.get("batch_size", 1))


async def reset_job_for_next_chapter(db: AsyncSession, job: Job, next_chapter: int) -> None:
    job.current_step = "planner"
    job.current_chapter = next_chapter + 1
    await db.commit()


async def decrement_remaining_chapters(db: AsyncSession, job: Job) -> None:
    params = get_job_params(job)
    if not params:
        return

    current_remaining = params.get("remaining_chapters", params.get("batch_size", 1))
    params["remaining_chapters"] = max(0, current_remaining - 1)
    set_job_params(job, params)
    await db.commit()


async def update_novel_status_on_finished(db: AsyncSession, novel: Novel) -> None:
    if not novel.target_chapters:
        novel.status = NovelStatus.PAUSED
        return

    ch_res = await db.execute(
        select(Chapter.chapter_index, Chapter.status)
        .where(Chapter.novel_id == novel.id, Chapter.chapter_index <= novel.target_chapters)
    )
    if all_target_chapters_published(ch_res.all(), novel.target_chapters):
        novel.status = NovelStatus.COMPLETED
    else:
        novel.status = NovelStatus.PAUSED
