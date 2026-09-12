from services.job_payload import (
    clear_job_error,
    find_experiment_params,
    get_job_params,
    set_job_params,
)
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.novel import Novel, Chapter, Job
from agents.constants import AGENT_PLANNER
from services.novel_constants import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_CHAPTER_INDEX,
    JOB_TYPE_GENERATE,
)
from services.chapter_progress import find_next_writable_chapter
from services.pipeline_transitions import StateMachine
from services.pipeline_types import JobStatus
from services.chapter_rewrite import reset_chapter_for_rewrite
from services.chapter_progress import is_frozen
from services.pipeline_commands import pause_project, resume_project
async def _get_novel(db: AsyncSession, project_id):
    novel = (await db.execute(select(Novel).where(Novel.id == project_id))).scalar_one_or_none()
    if novel is None:
        raise LookupError("Project not found")
    return novel


async def latest_generate_job_id(db: AsyncSession, project_id) -> Any:
    result = await db.execute(
        select(Job.id)
        .where(Job.project_id == project_id, Job.type == JOB_TYPE_GENERATE)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def generate(
    db: AsyncSession,
    project_id,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    word_count_per_chapter: int | None = None,
    experiment: dict | None = None,
):
    novel = await _get_novel(db, project_id)
    locked_novel = await db.execute(select(Novel).where(Novel.id == novel.id).with_for_update())
    novel = locked_novel.scalar_one()

    if word_count_per_chapter is not None:
        novel.word_count_per_chapter = word_count_per_chapter

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
        raise ValueError("该小说已有正在进行的生成任务，请等待或暂停后再试。")

    # Continuing a project creates a new Job. Preserve research metadata from
    # the previous generation job unless the caller explicitly overrides it.
    previous_job_result = await db.execute(
        select(Job)
        .where(Job.project_id == novel.id, Job.type == JOB_TYPE_GENERATE)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    previous_job = previous_job_result.scalar_one_or_none()
    previous_params = get_job_params(previous_job) if previous_job else {}
    job_payload = {
        "batch_size": batch_size
    }
    if previous_params.get("experiment"):
        job_payload["experiment"] = previous_params["experiment"]
    if experiment:
        job_payload["experiment"] = experiment

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


async def pause(db: AsyncSession, project_id):
    await pause_project(db, project_id)
    return {"status": "paused"}


async def resume(db: AsyncSession, project_id):
    job = await resume_project(db, project_id)
    return {"status": "resumed", "job_id": str(job.id)}










async def rewrite(
    db: AsyncSession,
    project_id,
    *,
    use_existing_outline: bool = True,
    custom_prompt: str | None = None,
    chapter_index: int | None = None,
):
    pid = project_id
    
    # Check if there is at least one chapter in the database
    result_ch = await db.execute(
        select(Chapter).where(Chapter.novel_id == pid)
    )
    chapters = result_ch.scalars().all()
    if not chapters:
        raise ValueError("没有章节，无法重写！")
        
    result = await db.execute(
        select(Job)
        .where(Job.project_id == pid, Job.type == JOB_TYPE_GENERATE)
        .order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()
    
    # Serialized rewrite configuration to carry in Job.error
    job_payload = {
        "use_existing_outline": use_existing_outline,
        "custom_prompt": custom_prompt,
    }
    
    if jobs:
        # Retry/Rewrite the most recent generate job
        job = jobs[0]

        target_chapter_index = chapter_index or job.current_chapter
        target_chapter = next((c for c in chapters if c.chapter_index == target_chapter_index), None)
        if target_chapter and is_frozen(target_chapter):
            raise ValueError("已发布章节不可重写")

        previous_params = get_job_params(job)

        job.status = JobStatus.PENDING
        experiment = find_experiment_params(jobs)
        if experiment:
            job_payload["experiment"] = experiment
        set_job_params(job, job_payload)
        clear_job_error(job)
        job.current_step = AGENT_PLANNER

        job.current_chapter = target_chapter_index

        if target_chapter:
            reset_chapter_for_rewrite(
                target_chapter,
                use_existing_outline=use_existing_outline,
                custom_prompt=custom_prompt,
            )
            target_chapter.rewrite_count = 0
            job.current_step = "writer" if use_existing_outline else AGENT_PLANNER

        # Cancel other active jobs
        for old_job in jobs[1:]:
            if old_job.status in [JobStatus.FAILED, JobStatus.PENDING, JobStatus.RUNNING]:
                old_job.status = JobStatus.CANCELLED
    else:
        # Fallback: create a new job if none exists
        target_chapter_index = chapter_index or DEFAULT_CHAPTER_INDEX
        target_chapter = next((c for c in chapters if c.chapter_index == target_chapter_index), None)
        if target_chapter and is_frozen(target_chapter):
            raise ValueError("已发布章节不可重写")
        job = Job(
            project_id=pid,
            type=JOB_TYPE_GENERATE,
            status=JobStatus.PENDING,
            current_chapter=target_chapter_index,
            current_step=AGENT_PLANNER,
            params=job_payload
        )
        db.add(job)

        if target_chapter:
            reset_chapter_for_rewrite(
                target_chapter,
                use_existing_outline=use_existing_outline,
                custom_prompt=custom_prompt,
            )

    # Resume novel state
    result_novel = await db.execute(select(Novel).where(Novel.id == pid))
    novel = result_novel.scalar_one_or_none()
    if novel:
        StateMachine.set_novel_generating(novel)

    await db.commit()
    return {"status": "retrying"}
