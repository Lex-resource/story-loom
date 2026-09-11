"""孤儿任务清理：将重启后仍处于 RUNNING 的陈旧 Job 标记为 FAILED。

提供两个入口：
- cleanup_orphaned_jobs(): 一次性清理（worker 启动时调用）
- cleanup_orphaned_jobs_periodic(): 周期性清理（worker 主循环并行任务）

"陈旧"判定：updated_at 距今超过 stale_job_threshold_seconds（runtime_tunables）。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from database import async_session
from agents.constants import AGENT_EXTRACTOR
from models.novel import Chapter, Job, Novel
from services.character_branch_service import recover_character_branch_job
from services.job_payload import append_job_error
from services.novel_constants import JOB_TYPE_CHARACTER_BRANCH
from services.pipeline_types import ChapterStatus, JobStatus, NovelStatus, PipelineStep
from services.runtime_tunables_service import get_value
from worker_support.task_registry import is_active

logger = logging.getLogger(__name__)


async def cleanup_orphaned_jobs() -> None:
    """启动时一次性清理：将陈旧 RUNNING Job 标记为 FAILED。"""
    logger.info("orphan_cleanup_started")
    try:
        # 孤儿阈值入库(runtime_tunables),每次清理时读取。必须显著大于单章内
        # 串行 LLM 调用的总耗时,否则会把卡在长调用里的健康任务误判为孤儿;
        # 同进程场景另有 task_registry.is_active() 兜底。
        stale_threshold = await get_value("stale_job_threshold_seconds")
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
                    logger.info("orphan_cleanup_skip_in_process job_id=%s", job.id)
                    continue
                updated = job.updated_at or job.created_at
                age = (now - updated).total_seconds() if updated else stale_threshold + 1
                if age < stale_threshold:
                    logger.info(
                        "orphan_cleanup_skip_fresh job_id=%s age_seconds=%i", job.id, int(age)
                    )
                    continue
                logger.warning("orphan_cleanup_found job_id=%s", job.id)
                job.status = JobStatus.FAILED
                append_job_error(job, "任务意外中断 (后台服务重启或被意外终止)")

                if job.type == JOB_TYPE_CHARACTER_BRANCH:
                    await recover_character_branch_job(
                        db,
                        job,
                        reason="支线生成任务在 Worker 重启前未完成，可重新生成",
                    )

                if job.type != JOB_TYPE_CHARACTER_BRANCH and job.current_step == AGENT_EXTRACTOR and job.current_chapter:
                    chapter_result = await db.execute(
                        select(Chapter).where(
                            Chapter.novel_id == job.project_id,
                            Chapter.chapter_index == job.current_chapter,
                        )
                    )
                    chapter = chapter_result.scalar_one_or_none()
                    if chapter and chapter.status == ChapterStatus.POST_PROCESSING:
                        chapter.pipeline_step = PipelineStep.EXTRACTING
                        chapter.status = ChapterStatus.POSTPROCESS_FAILED
                        chapter.error = (
                            "提取设定任务在 Worker 重启前未完成，正文已保留，"
                            "可从提取器步骤继续。"
                        )

                novel_res = await db.execute(select(Novel).where(Novel.id == job.project_id))
                novel = novel_res.scalar_one_or_none()
                if job.type != JOB_TYPE_CHARACTER_BRANCH and novel and novel.status == NovelStatus.GENERATING:
                    novel.status = NovelStatus.PAUSED
            await db.commit()
    except Exception:
        logger.exception("orphan_cleanup_failed")


async def cleanup_orphaned_jobs_periodic() -> None:
    """周期性清理：与 poll_jobs 并行运行，间隔入库可调（下一轮循环生效）。"""
    while True:
        interval = await get_value("orphan_cleanup_interval_seconds")
        await asyncio.sleep(interval)
        await cleanup_orphaned_jobs()
