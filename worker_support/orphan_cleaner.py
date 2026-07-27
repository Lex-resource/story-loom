"""孤儿任务清理：将重启后仍处于 RUNNING 的陈旧 Job 标记为 FAILED。

提供两个入口：
- cleanup_orphaned_jobs(): 一次性清理（worker 启动时调用）
- cleanup_orphaned_jobs_periodic(): 周期性清理（worker 主循环并行任务）

"陈旧"判定：updated_at 距今超过 STALE_THRESHOLD_SECONDS。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from database import async_session
from models.novel import Job, Novel
from services.job_payload import append_job_error
from services.pipeline_types import JobStatus, NovelStatus
from worker_support.task_registry import is_active


# Job 处于 RUNNING 但未更新超过该秒数视为孤儿（worker 已死/重启）。
# 必须显著大于单章内串行 LLM 调用的总耗时（LLM_TIMEOUT=180s，一章会跑
# planner/writer/editor/validator 多次），否则会把卡在长调用里的健康任务误判为孤儿。
# 同进程场景另有 task_registry.is_active() 兜底，此阈值主要覆盖跨进程 worker。
STALE_THRESHOLD_SECONDS = 600
# 周期清理间隔（秒）。
PERIODIC_INTERVAL_SECONDS = 300


async def cleanup_orphaned_jobs() -> None:
    """启动时一次性清理：将陈旧 RUNNING Job 标记为 FAILED。"""
    print("[orphan_cleaner] Cleaning up orphaned running jobs...")
    try:
        async with async_session() as db:
            result = await db.execute(
                select(Job).where(Job.status == JobStatus.RUNNING)
            )
            jobs = result.scalars().all()
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            for job in jobs:
                # 本进程仍在运行该任务：无论 DB 行多久没刷新（可能卡在一次长 LLM
                # 调用里），它都不是孤儿。这是防误杀的首要保险。
                if is_active(str(job.id)):
                    print(f"[orphan_cleaner] Skipping job {job.id} — still running in this process.")
                    continue
                updated = job.updated_at or job.created_at
                age = (now - updated).total_seconds() if updated else STALE_THRESHOLD_SECONDS + 1
                if age < STALE_THRESHOLD_SECONDS:
                    print(f"[orphan_cleaner] Skipping active job {job.id} (updated {age:.0f}s ago).")
                    continue
                print(f"[orphan_cleaner] Found orphaned running job {job.id}, marking as failed.")
                job.status = JobStatus.FAILED
                append_job_error(job, "任务意外中断 (后台服务重启或被意外终止)")

                novel_res = await db.execute(select(Novel).where(Novel.id == job.project_id))
                novel = novel_res.scalar_one_or_none()
                if novel and novel.status == NovelStatus.GENERATING:
                    novel.status = NovelStatus.PAUSED
            await db.commit()
    except Exception as e:
        print(f"[orphan_cleaner ERROR] cleanup failed: {e}")


async def cleanup_orphaned_jobs_periodic() -> None:
    """周期性清理：与 poll_jobs 并行运行，间隔 PERIODIC_INTERVAL_SECONDS 秒。"""
    while True:
        await asyncio.sleep(PERIODIC_INTERVAL_SECONDS)
        await cleanup_orphaned_jobs()
