"""进程内异步任务注册表。

跟踪由 poll_jobs 创建的 asyncio.Task，提供：
- register(job_id, task): 注册任务引用，避免被 GC
- cancel(job_id): 主动取消任务（用于 rewrite 端点抢占同 job 的旧任务）
- reap_finished(): 回收已完成任务，释放槽位
- has_capacity(): 判断是否还有并发槽位

单进程模型：所有 worker task 共享同一个 _active_tasks 字典。
"""
from __future__ import annotations

import asyncio

from config import settings


# job_id(str) -> asyncio.Task
_active_tasks: dict[str, asyncio.Task] = {}


def register(job_id: str, task: asyncio.Task) -> None:
    """注册一个 job task。若同一 job_id 已有旧任务，先取消并等待其退出。"""
    existing = _active_tasks.get(job_id)
    if existing is not None and not existing.done():
        existing.cancel()
    _active_tasks[job_id] = task


def cancel(job_id: str) -> bool:
    """取消指定 job 的活跃任务。返回 True 表示存在并已取消。"""
    task = _active_tasks.get(job_id)
    if task is None or task.done():
        return False
    task.cancel()
    return True


def reap_finished() -> None:
    """回收所有已完成任务，释放槽位。"""
    for jid in list(_active_tasks.keys()):
        task = _active_tasks[jid]
        if task.done():
            _active_tasks.pop(jid, None)


def has_capacity() -> bool:
    """判断当前活跃任务数是否在 MAX_CONCURRENT_JOBS 限制内。"""
    max_jobs = getattr(settings, "MAX_CONCURRENT_JOBS", None) or 3
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
