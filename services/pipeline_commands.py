"""Durable project commands shared by REST, WebSocket, and workers."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import AGENT_PLANNER
from models.novel import Chapter, Job, Novel
from services.job_payload import (
    clear_job_error,
    find_experiment_params,
    get_job_params,
    set_job_params,
)
from services.novel_constants import JOB_TYPE_GENERATE
from services.pipeline_transitions import StateMachine
from services.pipeline_types import JobStatus


ACTIVE_JOB_STATUSES = (JobStatus.PENDING, JobStatus.RUNNING)


async def latest_generate_job(db: AsyncSession, project_id: uuid.UUID, *, lock: bool = False) -> Job | None:
    query = (
        select(Job)
        .where(Job.project_id == project_id, Job.type == JOB_TYPE_GENERATE)
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    if lock:
        query = query.with_for_update()
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def experiment_params_for_project(
    db: AsyncSession, project_id: uuid.UUID
) -> dict | None:
    """Find experiment metadata across the project's generation history."""
    result = await db.execute(
        select(Job.params)
        .where(Job.project_id == project_id, Job.type == JOB_TYPE_GENERATE)
        .where(func.json_typeof(Job.params["experiment"]) == "object")
        .order_by(Job.created_at.desc())
        .limit(1)
    )
    candidate = result.scalar_one_or_none()
    if isinstance(candidate, dict):
        experiment = candidate.get("experiment")
        if isinstance(experiment, dict):
            return dict(experiment)
    elif candidate is not None:
        experiment = find_experiment_params([candidate])
        if experiment:
            return experiment

    # Older rows may have structured experiment metadata in the legacy error
    # column and no params JSON. Keep that compatibility path bounded.
    legacy_result = await db.execute(
        select(Job)
        .where(
            Job.project_id == project_id,
            Job.type == JOB_TYPE_GENERATE,
            Job.params.is_(None),
        )
        .order_by(Job.created_at.desc())
        .limit(100)
    )
    return find_experiment_params(legacy_result.scalars().all())


async def lock_project(db: AsyncSession, project_id: uuid.UUID) -> Novel | None:
    result = await db.execute(select(Novel).where(Novel.id == project_id).with_for_update())
    return result.scalar_one_or_none()


async def pause_project(db: AsyncSession, project_id: uuid.UUID) -> None:
    novel = await lock_project(db, project_id)
    result = await db.execute(
        select(Job)
        .where(Job.project_id == project_id, Job.status.in_(ACTIVE_JOB_STATUSES))
        .with_for_update()
    )
    for job in result.scalars().all():
        StateMachine.pause_job(job)

    if novel:
        StateMachine.set_novel_paused(novel)
    await db.commit()


async def reset_job_for_resume(db: AsyncSession, job: Job, project_id: uuid.UUID) -> None:
    """PAUSED/FAILED 任务的复位:置 PENDING、清错误、修 validator 锚点、
    保留实验元数据。resume_project 与 worker 控制的 retry 端点共用。"""
    job.status = JobStatus.PENDING
    params = get_job_params(job)
    params.pop("await_outline_review", None)
    if not isinstance(params.get("experiment"), dict):
        experiment = await experiment_params_for_project(db, project_id)
        if experiment:
            params["experiment"] = experiment
    set_job_params(job, params)
    clear_job_error(job)
    # A validator-blocked chapter needs a new Writer pass with the
    # validator's concrete instructions. Re-running Validator alone only
    # repeats the same rejection and can never repair the saved content.
    if job.current_step == "validator":
        job.current_step = "writer"
        # A terminal validator block is persisted after the normal rewrite
        # budget is exhausted.  Resuming must open one repair slot; keeping
        # the exhausted count would skip Writer and send the same draft
        # straight back to Validator.  The experiment recorder still
        # retains the original retry events, so this only controls the
        # in-memory pipeline budget for the resumed pass.
        chapter_query = await db.execute(
            select(Chapter)
            .where(
                Chapter.novel_id == project_id,
                Chapter.chapter_index == job.current_chapter,
            )
            .limit(1)
        )
        chapter = chapter_query.scalar_one_or_none()
        if chapter is not None and (chapter.rewrite_count or 0) > 0:
            chapter.rewrite_count -= 1
    else:
        job.current_step = job.current_step or AGENT_PLANNER


async def resume_project(db: AsyncSession, project_id: uuid.UUID) -> Job:
    novel = await lock_project(db, project_id)
    job = await latest_generate_job(db, project_id, lock=True)
    if job and job.status in ACTIVE_JOB_STATUSES:
        return job

    if job and job.status in (JobStatus.PAUSED, JobStatus.FAILED):
        await reset_job_for_resume(db, job, project_id)
    else:
        # Step-mode jobs are completed after each chapter. Continuing such a
        # project creates a new Job, so carry forward opt-in experiment
        # metadata; otherwise the next chapter loses prompt/version
        # recording and silently falls back to the production context.
        previous_params = get_job_params(job) if job else {}
        continuation_params = {}
        experiment = previous_params.get("experiment")
        if not isinstance(experiment, dict):
            experiment = await experiment_params_for_project(db, project_id)
        if experiment:
            continuation_params["experiment"] = experiment
        # Step-mode jobs finish after one chapter and persist
        # ``remaining_chapters: 0``. A manual resume is a new one-chapter
        # batch, so do not carry the exhausted counter into the new job.
        continuation_params["remaining_chapters"] = 1
        job = Job(
            project_id=project_id,
            type=JOB_TYPE_GENERATE,
            status=JobStatus.PENDING,
            current_step=AGENT_PLANNER,
            params=continuation_params or None,
        )
        db.add(job)

    if novel:
        StateMachine.set_novel_generating(novel)
    await db.commit()
    return job
