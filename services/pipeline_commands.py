"""Durable project commands shared by REST, WebSocket, and workers."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import AGENT_PLANNER
from models.novel import Job, Novel
from services.job_payload import clear_job_error, get_job_params, set_job_params
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


async def resume_project(db: AsyncSession, project_id: uuid.UUID) -> Job:
    novel = await lock_project(db, project_id)
    job = await latest_generate_job(db, project_id, lock=True)
    if job and job.status in ACTIVE_JOB_STATUSES:
        return job

    if job and job.status in (JobStatus.PAUSED, JobStatus.FAILED):
        job.status = JobStatus.PENDING
        params = get_job_params(job)
        params.pop("await_outline_review", None)
        set_job_params(job, params)
        clear_job_error(job)
        job.current_step = job.current_step or AGENT_PLANNER
    else:
        job = Job(
            project_id=project_id,
            type=JOB_TYPE_GENERATE,
            status=JobStatus.PENDING,
            current_step=AGENT_PLANNER,
        )
        db.add(job)

    if novel:
        StateMachine.set_novel_generating(novel)
    await db.commit()
    return job


async def set_intervention_prompt(db: AsyncSession, project_id: uuid.UUID, prompt: str) -> Job:
    normalized = prompt.strip()
    if not normalized:
        raise ValueError("intervention prompt must not be empty")
    await lock_project(db, project_id)
    job = await latest_generate_job(db, project_id, lock=True)
    if not job or job.status not in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.PAUSED):
        raise LookupError("no active generation job")
    job.intervention_prompt = normalized
    await db.commit()
    return job


async def get_intervention_prompt(db: AsyncSession, project_id: uuid.UUID) -> str:
    job = await latest_generate_job(db, project_id)
    return job.intervention_prompt or "" if job else ""


async def clear_intervention_prompt(db: AsyncSession, job: Job) -> None:
    if job.intervention_prompt:
        job.intervention_prompt = None
        await db.commit()
