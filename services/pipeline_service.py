from services.job_payload import clear_job_error
from typing import Optional
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.novel import Novel, Chapter, Job
from agents.constants import AGENT_PLANNER
from services.ids import parse_project_id
from services.novel_constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CHAPTER_INDEX,
    JOB_TYPE_GENERATE,
)
from services.chapter_progress import find_next_writable_chapter
from services.pipeline_transitions import StateMachine, set_chapter_pipeline_step
from services.pipeline_types import ChapterStatus, JobStatus, NovelStatus, PipelineStep
from services.chapter_rewrite import reset_chapter_for_rewrite
from services.pipeline_commands import pause_project, resume_project, set_intervention_prompt



class GenerateRequest(BaseModel):
    batch_size: int = Field(default=DEFAULT_BATCH_SIZE, ge=1, le=100)
    word_count_per_chapter: Optional[int] = Field(default=None, ge=0, le=100_000)


async def generate(project_id: str, data: Optional[GenerateRequest] = None, db: AsyncSession = Depends(get_db)):
    from services.project_service import get_novel_or_404
    parse_project_id(project_id)
    novel = await get_novel_or_404(db, project_id)
    locked_novel = await db.execute(select(Novel).where(Novel.id == novel.id).with_for_update())
    novel = locked_novel.scalar_one()

    batch_size = data.batch_size if data else DEFAULT_BATCH_SIZE
    word_count = data.word_count_per_chapter if data else None

    if word_count is not None:
        novel.word_count_per_chapter = word_count

    # Dynamically adjust target_chapters if next_chapter + batch_size - 1 exceeds it
    from models.novel import Chapter
    ch_res = await db.execute(
        select(Chapter.chapter_index, Chapter.status)
        .where(Chapter.novel_id == novel.id)
        .order_by(Chapter.chapter_index)
    )
    next_chapter = find_next_writable_chapter(ch_res.all(), novel.target_chapters)

    required_target = next_chapter + batch_size - 1
    if not novel.target_chapters or required_target > novel.target_chapters:
        novel.target_chapters = required_target

    # Prevent duplicate concurrent generate jobs for the same novel
    existing_job_res = await db.execute(
        select(Job).where(
            Job.project_id == novel.id,
            Job.type == JOB_TYPE_GENERATE,
            Job.status.in_([JobStatus.RUNNING, JobStatus.PENDING]),
        )
    )
    existing_job = existing_job_res.scalar_one_or_none()
    if existing_job:
        raise HTTPException(status_code=409, detail="该小说已有正在进行的生成任务，请等待或暂停后再试。")

    job_payload = {
        "batch_size": batch_size
    }

    job = Job(
        project_id=novel.id,
        type=JOB_TYPE_GENERATE,
        status=JobStatus.PENDING,
        current_step=AGENT_PLANNER,
        params=job_payload
    )
    db.add(job)
    StateMachine.set_novel_generating(novel)
    await db.commit()
    return {"job_id": str(job.id), "status": "pending"}


async def pause(project_id: str, db: AsyncSession = Depends(get_db)):
    pid = parse_project_id(project_id)
    await pause_project(db, pid)
    return {"status": "paused"}


async def resume(project_id: str, db: AsyncSession = Depends(get_db)):
    pid = parse_project_id(project_id)
    job = await resume_project(db, pid)
    return {"status": "resumed", "job_id": str(job.id)}


class InterventionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4_000)


async def intervene(project_id: str, data: InterventionRequest, db: AsyncSession = Depends(get_db)):
    pid = parse_project_id(project_id)
    try:
        job = await set_intervention_prompt(db, pid, data.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "accepted", "job_id": str(job.id)}







class RewriteRequest(BaseModel):
    use_existing_outline: bool = True
    custom_prompt: Optional[str] = Field(default=None, max_length=20_000)
    chapter_index: Optional[int] = Field(default=None, ge=1, le=10_000)


async def rewrite(project_id: str, data: RewriteRequest, db: AsyncSession = Depends(get_db)):
    pid = parse_project_id(project_id)
    
    # Check if there is at least one chapter in the database
    result_ch = await db.execute(
        select(Chapter).where(Chapter.novel_id == pid)
    )
    chapters = result_ch.scalars().all()
    if not chapters:
        raise HTTPException(status_code=400, detail="没有章节，无法重写！")
        
    result = await db.execute(
        select(Job)
        .where(Job.project_id == pid, Job.type == JOB_TYPE_GENERATE)
        .order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()
    
    # Serialized rewrite configuration to carry in Job.error
    job_payload = {
        "use_existing_outline": data.use_existing_outline,
        "custom_prompt": data.custom_prompt
    }
    
    if jobs:
        # Retry/Rewrite the most recent generate job
        job = jobs[0]

        job.status = JobStatus.PENDING
        job.params = job_payload
        clear_job_error(job)
        job.current_step = AGENT_PLANNER

        target_chapter_index = data.chapter_index or job.current_chapter
        job.current_chapter = target_chapter_index

        target_chapter = next((c for c in chapters if c.chapter_index == target_chapter_index), None)
        if target_chapter:
            reset_chapter_for_rewrite(
                target_chapter,
                use_existing_outline=data.use_existing_outline,
                custom_prompt=data.custom_prompt,
            )
            target_chapter.rewrite_count = 0
            job.current_step = "writer" if data.use_existing_outline else AGENT_PLANNER

        # Cancel other active jobs
        for old_job in jobs[1:]:
            if old_job.status in [JobStatus.FAILED, JobStatus.PENDING, JobStatus.RUNNING]:
                old_job.status = JobStatus.CANCELLED
    else:
        # Fallback: create a new job if none exists
        job = Job(
            project_id=pid,
            type=JOB_TYPE_GENERATE,
            status=JobStatus.PENDING,
            current_chapter=data.chapter_index or DEFAULT_CHAPTER_INDEX,
            current_step=AGENT_PLANNER,
            params=job_payload
        )
        db.add(job)

        target_chapter_index = data.chapter_index or DEFAULT_CHAPTER_INDEX
        target_chapter = next((c for c in chapters if c.chapter_index == target_chapter_index), None)
        if target_chapter:
            reset_chapter_for_rewrite(
                target_chapter,
                use_existing_outline=data.use_existing_outline,
                custom_prompt=data.custom_prompt,
            )

    # Resume novel state
    result_novel = await db.execute(select(Novel).where(Novel.id == pid))
    novel = result_novel.scalar_one_or_none()
    if novel:
        StateMachine.set_novel_generating(novel)

    await db.commit()
    return {"status": "retrying"}
