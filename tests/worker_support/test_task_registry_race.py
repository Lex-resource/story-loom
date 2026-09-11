"""S1/S2 稳定性修复回归测试：同 job 重注册竞态、cancel_and_wait、异常收割。

对应 docs/plans/2026-08-29-stability-fixes.md 的 S1（双跑竞态）与 S2（任务
异常无人收割）。不依赖数据库，全部用真实 asyncio.Task 驱动注册表。
"""
import asyncio
import logging
from types import SimpleNamespace

import pytest

from worker_support import task_registry


@pytest.fixture(autouse=True)
def _clean_registry():
    task_registry._active_tasks.clear()
    yield
    task_registry._active_tasks.clear()


def test_register_awaits_old_task_full_exit():
    """同 job_id 快速 re-register：旧任务必须完全退出后新任务才注册。"""

    async def scenario():
        old_started = asyncio.Event()

        async def old_job():
            old_started.set()
            try:
                await asyncio.Event().wait()  # 挂起直到被取消
            except asyncio.CancelledError:
                await asyncio.sleep(0.05)  # 模拟取消后的收尾工作
                raise

        async def new_job():
            await asyncio.Event().wait()

        old = asyncio.create_task(old_job())
        await old_started.wait()
        task_registry._active_tasks["job-1"] = old  # 旧任务已在上一轮 claim 注册
        new = asyncio.create_task(new_job())

        await task_registry.register("job-1", new)

        assert old.done()
        assert old.cancelled()
        assert task_registry._active_tasks["job-1"] is new
        new.cancel()

    asyncio.run(scenario())


def test_register_timeout_still_registers_and_logs(monkeypatch, caplog):
    """旧任务吞掉取消不肯退出时：限时放行并记 error，不拖死 poll_jobs。"""
    monkeypatch.setattr(task_registry, "_REGISTRATION_WAIT_TIMEOUT_SECONDS", 0.05)

    async def scenario():
        cancels = {"count": 0}

        async def stubborn():
            while True:
                try:
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    cancels["count"] += 1
                    if cancels["count"] >= 2:
                        return  # 第二次取消后放行，避免测试悬挂

        old = asyncio.create_task(stubborn())
        task_registry._active_tasks["job-1"] = old
        await asyncio.sleep(0.01)  # 让 stubborn 先跑到 sleep，cancel 才会被吞掉
        new = asyncio.create_task(asyncio.Event().wait())

        await task_registry.register("job-1", new)

        assert task_registry._active_tasks["job-1"] is new
        old.cancel()  # 第二次取消，让 stubborn 退出

    with caplog.at_level(logging.ERROR, logger="worker_support.task_registry"):
        asyncio.run(scenario())

    assert any("task_cancel_old_task_timeout" in r.message for r in caplog.records)


def test_reap_finished_logs_unretrieved_exception(caplog):
    """reap_finished 必须取走已完成任务的异常，不能等 GC 才报。"""

    async def scenario():
        async def boom():
            raise ValueError("escaped handler")

        task = asyncio.create_task(boom())
        task_registry._active_tasks["job-2"] = task
        await asyncio.sleep(0.05)  # 让任务带着未收割的异常结束

        assert task.done()
        with caplog.at_level(logging.ERROR, logger="worker_support.task_registry"):
            task_registry.reap_finished()

        assert "job-2" not in task_registry._active_tasks

    asyncio.run(scenario())

    assert any("job_task_unhandled_exception" in r.message for r in caplog.records)


def test_cancel_and_wait_returns_false_when_absent():
    async def scenario():
        assert await task_registry.cancel_and_wait("missing-job") is False

    asyncio.run(scenario())


def test_cancel_and_wait_waits_for_task_exit():
    async def scenario():
        async def job():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await asyncio.sleep(0.05)
                raise

        task = asyncio.create_task(job())
        task_registry._active_tasks["job-3"] = task

        cancelled = await task_registry.cancel_and_wait("job-3")

        assert cancelled is True
        assert task.done()

    asyncio.run(scenario())


def test_register_is_now_async():
    """register 必须是协程函数（同步实现会静默丢失等待语义）。"""
    import inspect

    assert inspect.iscoroutinefunction(task_registry.register)
    assert inspect.iscoroutinefunction(task_registry.cancel_and_wait)


def test_process_job_rolls_back_before_recovery_query(monkeypatch):
    """S2：handler 抛异常后，恢复查询前必须先 rollback，否则 DB 类失败时
    恢复路径自身再抛，job 永久 RUNNING。"""
    from services.pipeline_types import JobStatus
    from worker_support import orchestrator

    job = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        type="boom-handler",
        status=JobStatus.PENDING,
        project_id="22222222-2222-2222-2222-222222222222",
        current_step="writer",
        current_chapter=1,
        error=None,
        params={},
    )

    class _RecoverySession:
        def __init__(self):
            self.rolled_back = False
            self.order = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def rollback(self):
            self.rolled_back = True
            self.order.append("rollback")

        async def execute(self, statement):
            self.order.append("execute")
            return SimpleNamespace(
                scalar_one_or_none=lambda: job,
                scalars=lambda: SimpleNamespace(all=lambda: [job]),
            )

        async def refresh(self, obj):
            self.order.append("refresh")

        async def commit(self):
            self.order.append("commit")

    session = _RecoverySession()

    async def failing_handler(db, job):
        session.order.append("handler")
        raise RuntimeError("handler exploded")

    monkeypatch.setattr(orchestrator, "async_session", lambda: session)
    orchestrator.register_job_handler("boom-handler", failing_handler)
    monkeypatch.setattr(
        orchestrator,
        "StateMachine",
        SimpleNamespace(fail_job=lambda job: setattr(job, "status", JobStatus.FAILED)),
    )
    monkeypatch.setattr(
        orchestrator, "append_job_error", lambda job, msg, traceback="": None
    )
    monkeypatch.setattr(
        orchestrator, "_broadcast_error", _make_noop_broadcast()
    )

    try:
        asyncio.run(orchestrator.process_job(job.id))
    finally:
        orchestrator.JOB_HANDLERS.pop("boom-handler", None)

    assert session.rolled_back is True
    # rollback 必须发生在 handler 失败之后的第一次恢复查询之前
    assert session.order.index("rollback") < session.order.index(
        "execute", session.order.index("handler")
    )
    assert job.status == JobStatus.FAILED


def _make_noop_broadcast():
    async def _no_broadcast(job, e):
        return None

    return _no_broadcast
