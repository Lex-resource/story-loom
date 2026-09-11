"""API 启动时的陈旧 RUNNING job 恢复（仅内嵌 worker 模式调用）。

只把"陈旧"（超过 STALE_JOB_THRESHOLD_SECONDS 未刷新）的 RUNNING job 标
FAILED。配置漂移导致 API 以内嵌模式启动、而外部 worker 正在跑批量生成时，
无守卫的全量重置会把活任务整体标失败，因此新鲜 RUNNING 行不动，且存在
新鲜任务时跳过小说状态重置。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from database import async_session
from models.novel import Job, Novel
from services.character_branch_service import recover_character_branch_job
from services.job_payload import append_job_error
from services.novel_constants import JOB_TYPE_CHARACTER_BRANCH, JOB_TYPE_GENERATE
from services.pipeline_state import JobStatus, NovelStatus
from services.runtime_tunables_service import get_value

logger = logging.getLogger(__name__)


async def reset_stale_running_jobs() -> tuple[int, int]:
    """恢复陈旧 RUNNING job，返回 (failed_jobs, fresh_running)。"""
    try:
        stale_threshold = await get_value("stale_job_threshold_seconds")
        async with async_session() as session:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
                seconds=stale_threshold
            )
            last_activity = func.coalesce(Job.updated_at, Job.created_at)
            res_jobs = await session.execute(
                select(Job).where(Job.status == JobStatus.RUNNING, last_activity < cutoff)
            )
            running_jobs = res_jobs.scalars().all()
            for job in running_jobs:
                job.status = JobStatus.FAILED
                append_job_error(job, "服务器在执行中意外重启或中断")
                if getattr(job, "type", None) == JOB_TYPE_CHARACTER_BRANCH:
                    await recover_character_branch_job(
                        session,
                        job,
                        reason="支线生成任务在服务器重启前未完成，可重新生成",
                    )

            fresh_res = await session.execute(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.status == JobStatus.RUNNING,
                    Job.type == JOB_TYPE_GENERATE,
                    last_activity >= cutoff,
                )
            )
            fresh_running = fresh_res.scalar() or 0
            if fresh_running:
                # 有新鲜 RUNNING 行说明可能有活跃 worker 在跑，不要动小说状态。
                logger.info(
                    "startup_job_recovery_skipped_active fresh_running_jobs=%s",
                    fresh_running,
                )
            else:
                await session.execute(
                    update(Novel)
                    .where(Novel.status == NovelStatus.GENERATING)
                    .values(status=NovelStatus.PAUSED)
                )
            await session.commit()
            logger.info("startup_job_recovery_completed jobs=%s", len(running_jobs))
            return len(running_jobs), fresh_running
    except Exception:
        logger.exception("startup_job_recovery_failed")
        return 0, 0
