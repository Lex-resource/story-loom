"""worker 控制面（DB/查询部分）。

分层约束：本模块在 services 层，**不得 import worker_support**（架构测试
tests/architecture/test_service_boundaries）。task_registry 的进程内操作
（active_count / cancel_and_wait）由 routers/worker_admin.py 直接调用。

控制面数据存 runtime_tunables / jobs 表，外部 worker 模式同样受益 ——
API 进程改开关，worker 进程靠 TTL 缓存在下一轮认领时生效。
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import Job, Novel
from services.novel_constants import JOB_TYPE_CHARACTER_BRANCH, JOB_TYPE_GENERATE
from services.pipeline_commands import ACTIVE_JOB_STATUSES
from services.pipeline_transitions import StateMachine
from services.pipeline_types import JobStatus, NovelStatus
from services.runtime_tunables_service import get_value, update_values


async def worker_status() -> dict:
    """队列与开关快照（进程内 task_registry 状态由 router 附加）。"""
    from config import settings

    claim_paused = await get_value("worker_claim_paused")
    async with _session() as db:
        pending = (
            await db.execute(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.PENDING)
            )
        ).scalar_one()
        running = (
            await db.execute(
                select(func.count()).select_from(Job).where(Job.status == JobStatus.RUNNING)
            )
        ).scalar_one()
        running_jobs = (
            await db.execute(
                select(Job.id, Job.project_id, Job.current_step, Job.current_chapter)
                .where(Job.status == JobStatus.RUNNING)
                .order_by(Job.created_at)
            )
        ).all()
        pending_jobs_list = (
            await db.execute(
                select(Job.id, Job.project_id, Job.type, Job.created_at)
                .where(Job.status == JobStatus.PENDING)
                .order_by(Job.created_at)
                .limit(20)
            )
        ).all()
        retryable_jobs = (
            await db.execute(
                select(
                    Job.id,
                    Job.project_id,
                    Job.type,
                    Job.status,
                    Job.current_step,
                    Job.current_chapter,
                    Job.error,
                )
                .where(Job.status.in_([JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED]))
                .order_by(Job.updated_at.desc())
                .limit(20)
            )
        ).all()

    return {
        "mode": "external" if settings.DISABLE_IN_PROCESS_WORKER.lower() == "true" else "in_process",
        "claim_paused": claim_paused,
        "pending_jobs": int(pending),
        "running_jobs": int(running),
        "running_list": [
            {
                "job_id": str(row.id),
                "project_id": str(row.project_id),
                "current_step": row.current_step,
                "current_chapter": row.current_chapter,
            }
            for row in running_jobs
        ],
        "pending_list": [
            {
                "job_id": str(row.id),
                "project_id": str(row.project_id),
                "type": row.type,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in pending_jobs_list
        ],
        "retryable_list": [
            {
                "job_id": str(row.id),
                "project_id": str(row.project_id),
                "type": row.type,
                "status": str(row.status),
                "current_step": row.current_step,
                "current_chapter": row.current_chapter,
                "error": _error_snippet(row.error),
            }
            for row in retryable_jobs
        ],
        "orphan_cleanup_interval_seconds": await get_value("orphan_cleanup_interval_seconds"),
        "max_concurrent_jobs": await get_value("max_concurrent_jobs"),
    }


async def set_claim_paused(paused: bool) -> dict:
    return await update_values({"worker_claim_paused": bool(paused)})


async def cancel_job(db: AsyncSession, job_id: uuid.UUID) -> Job | None:
    """把任务置 CANCELLED；generate 任务的 novel 离开 GENERATING 置 PAUSED。

    终态任务（COMPLETED/FAILED/CANCELLED）拒绝再取消，返回 None 由 router
    转 409。不动 current_step —— 保留 resume 锚点语义。进程内的 asyncio
    任务取消由 router 先调 task_registry.cancel_and_wait（分层见模块头）。
    """
    job = await db.get(Job, job_id)
    if job is None:
        return None
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        return None
    novel = None
    if job.type == JOB_TYPE_GENERATE:
        novel_res = await db.execute(select(Novel).where(Novel.id == job.project_id))
        novel = novel_res.scalar_one_or_none()
    elif job.type == JOB_TYPE_CHARACTER_BRANCH:
        from services.character_branch_service import stop_character_branch_job

        await stop_character_branch_job(db, job)
    StateMachine.cancel_job(job, novel=novel)
    await db.commit()
    return job


async def retry_job(db: AsyncSession, job_id: uuid.UUID) -> Job | None:
    """复位一个可重试的任务：PAUSED/FAILED/CANCELLED → PENDING。

    复位路径与 resume_project 共用（reset_job_for_resume）：清错误、
    validator 锚点退回 writer 并开一个修复槽。运行中/排队中的任务拒绝重试。
    """
    job = await db.get(Job, job_id)
    if job is None:
        return None
    if job.status in ACTIVE_JOB_STATUSES or job.status == JobStatus.COMPLETED:
        return None

    from services.pipeline_commands import reset_job_for_resume

    await reset_job_for_resume(db, job, job.project_id)
    if job.type == JOB_TYPE_GENERATE:
        novel_res = await db.execute(select(Novel).where(Novel.id == job.project_id))
        novel = novel_res.scalar_one_or_none()
        if novel and novel.status != NovelStatus.GENERATING:
            StateMachine.set_novel_generating(novel)
    await db.commit()
    return job


def _error_snippet(error: str | None, limit: int = 120) -> str | None:
    """错误摘要:取最后一行并截断,给前端列表用。"""
    if not error:
        return None
    text = str(error).strip().splitlines()[-1].strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _session():
    from database import async_session

    return async_session()
