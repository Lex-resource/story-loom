"""进程内异步任务注册表。

跟踪由 poll_jobs 创建的 asyncio.Task，提供：
- register(job_id, task): 注册任务引用，避免被 GC
- cancel(job_id): 主动取消任务（同步，只调度取消不等待）
- cancel_and_wait(job_id): 取消并等待任务退出（rewrite 端点抢占用）
- reap_finished(): 回收已完成任务，释放槽位
- has_capacity(): 判断是否还有并发槽位

单进程模型：所有 worker task 共享同一个 _active_tasks 字典。
"""
from __future__ import annotations

import asyncio
import logging

from services.runtime_tunables_service import get_value_sync

logger = logging.getLogger(__name__)


# job_id(str) -> asyncio.Task
_active_tasks: dict[str, asyncio.Task] = {}

# register() 等待旧任务退出的上限。cancel() 只调度取消，旧任务要到下一个
# await 点才真正退出；不等待就换注册项会让同一 job 的新旧任务短暂并发跑。
# 但也不能无限等：旧任务若卡在无法取消的 executor 段里，等待会拖死
# poll_jobs —— 超时后放行并记 error（chroma 等 executor 调用另有超时兜底）。
_REGISTRATION_WAIT_TIMEOUT_SECONDS = 10.0


async def _cancel_and_wait(task: asyncio.Task, job_id: str) -> None:
    task.cancel()
    await asyncio.wait({task}, timeout=_REGISTRATION_WAIT_TIMEOUT_SECONDS)
    if task.done():
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "task_cancel_old_task_failed job_id=%s", job_id, exc_info=task.exception()
            )
    else:
        logger.error(
            "task_cancel_old_task_timeout job_id=%s wait_seconds=%s",
            job_id,
            _REGISTRATION_WAIT_TIMEOUT_SECONDS,
        )


async def register(job_id: str, task: asyncio.Task) -> None:
    """注册一个 job task。若同一 job_id 已有旧任务，先取消并等待其退出。"""
    existing = _active_tasks.get(job_id)
    if existing is not None and not existing.done():
        await _cancel_and_wait(existing, job_id)
    _active_tasks[job_id] = task


async def cancel_and_wait(job_id: str) -> bool:
    """取消指定 job 的活跃任务并等待其退出。返回 True 表示存在并已取消。"""
    task = _active_tasks.get(job_id)
    if task is None or task.done():
        return False
    await _cancel_and_wait(task, job_id)
    return True


def cancel(job_id: str) -> bool:
    """取消指定 job 的活跃任务。返回 True 表示存在并已取消。

    只调度取消，不等待退出；需要确保旧任务完全退出时用 cancel_and_wait。
    """
    task = _active_tasks.get(job_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def reap_finished() -> None:
    """回收所有已完成任务，释放槽位。

    已完成任务必须取一次 exception()，否则逃逸的异常只在 GC 时以
    "Task exception was never retrieved" 出现，失败无人知晓。
    """
    for jid in list(_active_tasks.keys()):
        task = _active_tasks[jid]
        if task.done():
            _active_tasks.pop(jid, None)
            if not task.cancelled() and task.exception() is not None:
                logger.error(
                    "job_task_unhandled_exception job_id=%s", jid, exc_info=task.exception()
                )


async def cancel_all_and_wait() -> None:
    """取消全部活跃任务并等待退出（进程 shutdown 时用）。"""
    items = [(jid, task) for jid, task in _active_tasks.items() if not task.done()]
    for _jid, task in items:
        task.cancel()
    if items:
        results = await asyncio.gather(
            *(task for _jid, task in items), return_exceptions=True
        )
        for (jid, _task), result in zip(items, results):
            if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.error(
                    "job_task_unhandled_exception job_id=%s", jid, exc_info=result
                )
    _active_tasks.clear()


def has_capacity() -> bool:
    """判断当前活跃任务数是否在 MAX_CONCURRENT_JOBS 限制内。"""
    # 同步读点(不能 await):读进程内快照,worker 轮询循环里的异步读点驱动刷新。
    max_jobs = get_value_sync("max_concurrent_jobs")
    return len(_active_tasks) < max_jobs


def is_active(job_id: str) -> bool:
    """该 job 是否有一个仍在运行的任务注册在本进程。

    孤儿清理器用它区分"进程死了留下的陈旧 RUNNING 行"与"本进程正在跑、
    只是卡在一次长 LLM 调用里、DB 行暂时没刷新"的健康任务。
    """
    task = _active_tasks.get(job_id)
    return task is not None and not task.done()


def active_count() -> int:
    """当前活跃任务数（调试用）。"""
    return len(_active_tasks)
