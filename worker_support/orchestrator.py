"""任务调度器：轮询待处理任务、分配并发槽位、处理状态流转。

本模块仅负责调度。实际的章节生成逻辑在 worker_support/generate_job_runner.py，
向量同步在 worker_support/vector_outbox_worker.py，孤儿任务清理在
worker_support/orphan_cleaner.py。

worker.py（外部模式）与 main.py lifespan（内嵌模式）共用 bootstrap_worker_context
+ start_worker_loops —— 本模块是工作循环的唯一装配点。
"""
from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models.novel import IssueSummary, Job, Novel
from services.novel_constants import (
    JOB_TYPE_CHARACTER_BRANCH,
    JOB_TYPE_GENERATE,
    JOB_TYPE_POST_PROCESSING,
    OPTIMIZED_ISSUE_SUMMARY_PREFIX,
)
from services.job_payload import append_job_error, get_job_params
from services.pipeline_transitions import StateMachine
from services.pipeline_types import JobStatus, NovelStatus
from services.runtime_tunables_service import get_value
from worker_support.generation_exceptions import JobAbortedException, JobPausedException
from worker_support.generation_job_batch_runner import process_generate_job
from worker_support.orphan_cleaner import cleanup_orphaned_jobs_periodic
from worker_support.task_registry import (
    active_count,
    reap_finished,
    register as register_task,
)

logger = logging.getLogger(__name__)
from worker_support.vector_outbox_worker import poll_vector_outbox
from worker_support.character_branch_job import process_character_branch_job
from worker_support.post_processing_job import process_post_processing_job

# ---------------------------------------------------------------------------
# 向后兼容 re-exports
# ---------------------------------------------------------------------------
# 以下符号历史上从 orchestrator 导出，外部代码（worker.py / tests）仍可能引用。
# 保留 re-export 以避免破坏导入契约。


# ---------------------------------------------------------------------------
# Job 处理器策略表
# ---------------------------------------------------------------------------
# 新增一种 Job 类型（如 extract_only / compact_living_docs）只需在此注册一个
# handler 和一个可选的 novel-status 门控函数，无需在 process_job / poll_jobs 里
# 加 if/elif 分支。

JobHandler = Callable[[AsyncSession, Job], Awaitable[None]]
NovelStatusGate = Callable[[str | None], bool]


def _generate_status_gate(novel_status: str | None) -> bool:
    """generate 类型 Job 仅在小说处于 GENERATING 时才允许执行。"""
    return novel_status == NovelStatus.GENERATING


def _always_run(novel_status: str | None) -> bool:
    """不依赖小说状态的 Job（如纯提取/清理）始终允许执行。"""
    return True


JOB_HANDLERS: dict[str, tuple[JobHandler, NovelStatusGate]] = {
    JOB_TYPE_GENERATE: (process_generate_job, _generate_status_gate),
    JOB_TYPE_CHARACTER_BRANCH: (process_character_branch_job, _always_run),
    JOB_TYPE_POST_PROCESSING: (process_post_processing_job, _always_run),
}


def register_job_handler(
    job_type: str, handler: JobHandler, gate: NovelStatusGate | None = None
) -> None:
    """注册一个新的 Job 类型处理器。

    gate 为 None 时默认使用 _always_run（不依赖小说状态）。
    """
    JOB_HANDLERS[job_type] = (handler, gate or _always_run)


def _get_job_handler(job_type: str) -> tuple[JobHandler, NovelStatusGate] | None:
    return JOB_HANDLERS.get(job_type)


async def check_paused(db: AsyncSession, job_id: uuid.UUID):
    result = await db.execute(select(Job.status).where(Job.id == job_id))
    status = result.scalar_one_or_none()
    if status == JobStatus.PAUSED:
        raise JobPausedException("Job was paused by user.")
    if status != JobStatus.RUNNING:
        raise JobAbortedException(f"Job status changed to {status}. Aborting execution.")


async def process_job(job_id: str, already_running: bool = False):
    async with async_session() as db:
        result = await db.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
        job = result.scalar_one_or_none()
        if not job:
            return
        if not already_running and job.status != JobStatus.PENDING:
            return

        if not already_running:
            job.status = JobStatus.RUNNING
            await db.commit()

        try:
            handler_entry = _get_job_handler(job.type)
            if handler_entry is None:
                raise ValueError(f"Unsupported job type: {job.type}")
            handler, _gate = handler_entry
            await handler(db, job)
            if job.status not in [
                JobStatus.PAUSED,
                JobStatus.CANCELLED,
                JobStatus.PENDING,
            ]:
                StateMachine.complete_job(job)
                # issue_id is stored in job params, not in job.error (which
                # is reserved for error messages via append_job_error).
                job_params = get_job_params(job)
                issue_id = job_params.get("issue_id")
                if issue_id:
                    try:
                        issue_res = await db.execute(
                            select(IssueSummary).where(
                                IssueSummary.id == uuid.UUID(issue_id)
                            )
                        )
                        issue = issue_res.scalar_one_or_none()
                        if issue:
                            issue.enabled = False
                            if not issue.summary.startswith(OPTIMIZED_ISSUE_SUMMARY_PREFIX):
                                issue.summary = f"{OPTIMIZED_ISSUE_SUMMARY_PREFIX} {issue.summary}"
                            await db.commit()
                    except Exception:
                        logger.exception("issue_optimization_mark_failed job_id=%s issue_id=%s", job_id, issue_id)
        except Exception as e:
            # handler 可能留下处于 pending-rollback 状态的 session（DB 类异常），
            # 不先 rollback 的话下面的恢复查询自身会再抛，job 永久卡 RUNNING。
            await db.rollback()
            job_res = await db.execute(select(Job).where(Job.id == uuid.UUID(job_id)))
            job = job_res.scalar_one_or_none()
            if not job:
                return
            await db.refresh(job)
            if job.status == JobStatus.RUNNING:
                StateMachine.fail_job(job)
                append_job_error(job, str(e), traceback=traceback.format_exc())
                try:
                    await _broadcast_error(job, e)
                except Exception:
                    logger.exception("job_error_broadcast_failed job_id=%s", job_id)
                await db.commit()
            else:
                # Job was already PAUSED/CANCELLED — log the error so it is
                # not silently swallowed, but do not overwrite the status.
                logger.exception("job_failed_after_status_change job_id=%s status=%s", job_id, job.status)
                append_job_error(job, str(e), traceback=traceback.format_exc())
                try:
                    await db.commit()
                except Exception:
                    logger.exception("job_error_commit_failed job_id=%s", job_id)
        finally:
            try:
                await db.refresh(job)
                if job.status in [
                    JobStatus.RUNNING,
                    JobStatus.COMPLETED,
                    JobStatus.FAILED,
                ]:
                    job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    await db.commit()
            except Exception:
                logger.exception("job_timestamp_update_failed job_id=%s", job_id)


async def _broadcast_error(job, e: Exception) -> None:
    """广播任务失败错误（容错，失败不应影响主流程）。"""
    from services.stream_manager import stream_manager

    await stream_manager.broadcast(
        str(job.project_id), "error", {"message": f"创作流异常中断: {e}"}
    )


async def claim_pending_jobs(limit: int) -> list[str]:
    """Atomically claim up to ``limit`` eligible jobs for this worker.

    PostgreSQL row locks make this safe across multiple worker processes. The
    status transition happens before tasks are created, so a crashed worker
    cannot leave another worker believing the same pending row is available.
    """
    if limit <= 0:
        return []

    # 全局暂停领取（runtime_tunables 的 worker_claim_paused，前端可切）：
    # paused 直接不领新任务，**在跑任务继续到检查点** —— 匹配"随时暂停随时
    # 介入"的语义，不是杀任务。TTL 缓存使开关秒级生效且不给 DB 加压力。
    if await get_value("worker_claim_paused"):
        return []

    async with async_session() as db:
        async with db.begin():
            result = await db.execute(
                select(Job, Novel.status)
                .outerjoin(Novel, Job.project_id == Novel.id)
                .where(Job.status == JobStatus.PENDING)
                .order_by(Job.created_at)
                .with_for_update(of=Job, skip_locked=True)
                .limit(max(limit * 4, 32))
            )
            claimed: list[str] = []
            for job, novel_status in result.all():
                if len(claimed) >= limit:
                    break
                handler_entry = _get_job_handler(job.type)
                if handler_entry is None:
                    job.status = JobStatus.FAILED
                    append_job_error(job, f"Unsupported job type: {job.type}")
                    continue
                _handler, gate = handler_entry
                if not gate(novel_status):
                    continue
                job.status = JobStatus.RUNNING
                claimed.append(str(job.id))
            return claimed


async def poll_jobs():
    while True:
        try:
            reap_finished()
            # 并发上限入库(runtime_tunables):每轮循环读取,前端改完下一轮生效。
            max_jobs = await get_value("max_concurrent_jobs")
            capacity = max(0, max_jobs - active_count())
            claimed_ids = await claim_pending_jobs(capacity)
        except Exception:
            logger.exception("job_poll_claim_failed")
            claimed_ids = []

        for job_id in claimed_ids:
            task = asyncio.create_task(process_job(job_id, already_running=True))
            await register_task(job_id, task)

        await asyncio.sleep(await get_value("worker_poll_interval_seconds"))


async def bootstrap_worker_context() -> None:
    """worker 启动引导：init_db + tokenizer/chroma 预热 + workflow_registry 刷新。

    worker.py（外部模式）与 main.py lifespan（内嵌模式）共用，保证两条入口
    的预热与装配行为一致 —— 这是"单进程为默认"后唯一的工作循环装配点。
    """
    from database import init_db
    from config import settings

    await init_db()

    # 预热 tokenizer：首次 AutoTokenizer.from_pretrained 是数秒级磁盘加载，
    # 不预热的话会卡在第一次 LLM 调用里。
    try:
        from services.token_count import preload_tokenizer

        if await asyncio.to_thread(preload_tokenizer):
            logger.info("tokenizer_preloaded")
    except Exception:
        logger.exception("tokenizer_preload_failed")

    # 预热 chroma：打开 client、读写探针、embedding 会话建立。把首次 ONNX
    # 下载/推理这类挂死源移出热路径，启动期就暴露"兜底召回不可用"。
    if settings.CHROMA_WARMUP_ENABLED:
        try:
            from services.vector_chroma import preload_chroma

            ok = await asyncio.to_thread(preload_chroma)
            logger.info("chroma_preloaded ok=%s", ok)
        except Exception:
            logger.exception("chroma_preload_failed")

    # 预热工作流缓存。`workflow_surface.strategy_for()` 在提示词组装的同步热路径上被
    # 调用，拿不到 session；`get_pipeline_config` 每章会顺手填充，但独立 worker 里
    # 有些路径（记忆合并、完结审校）会在那之前就问表面策略。静态兜底覆盖内置两行，
    # 这里是为了让**自定义工作流**从第一个任务起就正确。
    try:
        from services import workflow_registry

        async with async_session() as session:
            count = await workflow_registry.refresh(session)
        logger.info("workflow_registry_loaded workflows=%s", count)
    except Exception:
        logger.exception("workflow_registry_load_failed")


def start_worker_loops() -> dict[str, "asyncio.Task"]:
    """启动三个工作循环（job 轮询 / 向量外发 / 孤儿清理），返回句柄供收尾取消。

    在已运行的事件循环里调用（FastAPI lifespan 或 worker.py 的 asyncio.run）。
    """
    from worker_support.orphan_cleaner import cleanup_orphaned_jobs_periodic

    return {
        "jobs_task": asyncio.create_task(poll_jobs()),
        "vector_task": asyncio.create_task(poll_vector_outbox()),
        "orphan_cleanup_task": asyncio.create_task(cleanup_orphaned_jobs_periodic()),
    }
