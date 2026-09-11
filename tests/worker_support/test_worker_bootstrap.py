"""worker 启动编排测试:bootstrap_worker_context 与 start_worker_loops 的装配。

worker.py 的 gather 组合历史上零覆盖;归一后装配点在 orchestrator,这里
守住"两条入口(外部 worker.py / 内嵌 lifespan)行为一致"的契约。
"""
import asyncio

import pytest

from worker_support import orchestrator


def test_bootstrap_worker_context_runs_all_steps(monkeypatch):
    calls = []

    import database

    async def fake_init_db():
        calls.append("init_db")

    monkeypatch.setattr(database, "init_db", fake_init_db)

    from services import token_count

    def fake_preload_tokenizer():
        calls.append("tokenizer")
        return True

    monkeypatch.setattr(token_count, "preload_tokenizer", fake_preload_tokenizer)

    from config import settings

    monkeypatch.setattr(settings, "CHROMA_WARMUP_ENABLED", False)  # 关掉避免触碰 chroma

    from services import workflow_registry

    async def fake_refresh(session):
        calls.append("workflow_registry")
        return 2

    monkeypatch.setattr(workflow_registry, "refresh", fake_refresh)

    asyncio.run(orchestrator.bootstrap_worker_context())

    assert calls == ["init_db", "tokenizer", "workflow_registry"]


def test_bootstrap_worker_context_survives_preload_failures(monkeypatch):
    """预热失败不阻塞启动(可用性优先,各步骤独立兜底)。"""
    import database

    async def fake_init_db():
        pass

    monkeypatch.setattr(database, "init_db", fake_init_db)

    from services import token_count

    def boom():
        raise RuntimeError("no tokenizer")

    monkeypatch.setattr(token_count, "preload_tokenizer", boom)

    from config import settings

    monkeypatch.setattr(settings, "CHROMA_WARMUP_ENABLED", False)

    from services import workflow_registry

    async def boom_refresh(session):
        raise RuntimeError("db gone")

    monkeypatch.setattr(workflow_registry, "refresh", boom_refresh)

    asyncio.run(orchestrator.bootstrap_worker_context())  # 不抛即通过


def test_start_worker_loops_returns_three_cancellable_tasks(monkeypatch):
    started = []

    async def fake_jobs():
        started.append("jobs")
        await asyncio.sleep(30)

    async def fake_vector():
        started.append("vector")
        await asyncio.sleep(30)

    async def fake_orphan():
        started.append("orphan")
        await asyncio.sleep(30)

    monkeypatch.setattr(orchestrator, "poll_jobs", fake_jobs)
    monkeypatch.setattr(orchestrator, "poll_vector_outbox", fake_vector)

    from worker_support import orphan_cleaner

    monkeypatch.setattr(orphan_cleaner, "cleanup_orphaned_jobs_periodic", fake_orphan)

    async def scenario():
        loops = orchestrator.start_worker_loops()
        try:
            assert set(loops) == {"jobs_task", "vector_task", "orphan_cleanup_task"}
            await asyncio.sleep(0.01)  # 让三个任务都跑起来
            assert sorted(started) == ["jobs", "orphan", "vector"]
        finally:
            for task in loops.values():
                task.cancel()
            await asyncio.gather(*loops.values(), return_exceptions=True)

    asyncio.run(scenario())
