"""S10 回归测试：chroma 全局锁获取与 executor 操作必须有超时。

一个挂死的 chroma 操作不能冻结进程内所有向量读写。超时向调用方抛
TimeoutError（recall 调用方按"异常→空记忆"降级），且锁必须被释放，
后续操作能继续。超时值现在从 runtime_tunables 快照读取，测试用
freeze_tunables 覆盖。
"""
import asyncio
import time

import pytest

pytest.importorskip("chromadb")

from services import vector_chroma


@pytest.fixture(autouse=True)
def _fresh_lock():
    vector_chroma._chroma_lock = asyncio.Lock()
    yield
    vector_chroma._chroma_lock = asyncio.Lock()


@pytest.fixture(autouse=True)
def _frozen_tunables(freeze_tunables):
    freeze_tunables()
    yield


def test_operation_timeout_raises_and_releases_lock(freeze_tunables):
    freeze_tunables(
        chroma_operation_timeout_seconds=0.05,
        # 占用期阈值调小:挂死操作自身超时即触发 executor 隔离,后续操作走
        # 新线程"立即可用"(不隔离的话,后续操作会在僵尸后面排队直到占用期
        # 越过阈值)。
        chroma_zombie_threshold_seconds=0.02,
    )

    async def scenario():
        def hang():
            time.sleep(0.5)  # 模拟挂死的 chroma 调用（executor 线程里）

        with pytest.raises(TimeoutError):
            await vector_chroma.run_with_chroma(hang)

        # 锁必须已释放：后续正常操作立即可用
        def quick():
            return "ok"

        assert await vector_chroma.run_with_chroma(quick) == "ok"
        assert not vector_chroma._chroma_lock.locked()

    asyncio.run(scenario())


def test_lock_acquire_timeout(freeze_tunables):
    freeze_tunables(chroma_lock_acquire_timeout_seconds=0.05)

    async def scenario():
        await vector_chroma._chroma_lock.acquire()  # 模拟他人长期持有锁
        try:
            with pytest.raises(TimeoutError):
                await vector_chroma.run_with_chroma(lambda: "never")
        finally:
            vector_chroma._chroma_lock.release()

    asyncio.run(scenario())


def test_normal_operation_unchanged():
    async def scenario():
        def work(value):
            return value * 2

        assert await vector_chroma.run_with_chroma(work, 21) == 42
        assert not vector_chroma._chroma_lock.locked()

    asyncio.run(scenario())


def test_operations_serialize_on_dedicated_thread():
    """串行性:并发的两个 chroma 操作必须落到同一条专用线程顺序执行。"""
    import threading

    threads = []

    async def scenario():
        def work(value):
            threads.append(threading.current_thread().ident)
            time.sleep(0.05)
            return value

        return await asyncio.gather(
            vector_chroma.run_with_chroma(work, 1),
            vector_chroma.run_with_chroma(work, 2),
        )

    results = asyncio.run(scenario())
    assert results == [1, 2]
    assert len(threads) == 2
    assert threads[0] == threads[1]


def test_zombie_executor_recycled_and_new_thread_serves(freeze_tunables):
    """僵尸隔离:超时且耗时超过阈值 → 旧 executor 被隔离,后续操作走新线程成功。"""
    import threading

    freeze_tunables(
        chroma_operation_timeout_seconds=0.05,
        chroma_zombie_threshold_seconds=0.02,
    )
    old_executor = vector_chroma._chroma_executor
    zombie_thread: list[int] = []
    next_thread: list[int] = []

    async def scenario():
        def hang():
            zombie_thread.append(threading.current_thread().ident)
            time.sleep(0.4)  # 模拟不可取消的僵尸

        # 挂死操作自身超时时占用期(0.05)已越过阈值(0.02)→ 抛隔离错误
        with pytest.raises(vector_chroma.ChromaZombieIsolatedError):
            await vector_chroma.run_with_chroma(hang)

        # executor 已被换新
        assert vector_chroma._chroma_executor is not old_executor

        def quick():
            next_thread.append(threading.current_thread().ident)
            return "ok"

        assert await vector_chroma.run_with_chroma(quick) == "ok"

    asyncio.run(scenario())
    assert zombie_thread and next_thread
    assert zombie_thread[0] != next_thread[0]


def test_query_timeout_retries_once_on_fresh_executor(freeze_tunables, monkeypatch):
    """召回超时 → executor 已隔离 → 立即在新线程重试一次成功。"""
    freeze_tunables(
        chroma_operation_timeout_seconds=0.05,
        chroma_zombie_threshold_seconds=0.02,
    )
    calls = {"n": 0}

    class _FakeCollection:
        def query(self, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                time.sleep(0.3)  # 首次挂死 → 超时 + 僵尸重建
            return {"ids": [["a"]]}

    async def fake_embeddings(_texts):
        return None, 0  # 走 query_texts 路径,不触碰 embedding API

    monkeypatch.setattr(vector_chroma, "get_embeddings_from_api", fake_embeddings)
    monkeypatch.setattr(
        vector_chroma, "get_or_create_collection", lambda _name: _FakeCollection()
    )

    res = asyncio.run(vector_chroma.query_collection("col_x", ["q"]))
    assert res == {"ids": [["a"]]}
    assert calls["n"] == 2


def test_orphan_from_old_generation_does_not_clobber_started_at(freeze_tunables):
    """代际守卫:被隔离旧线程上的孤儿 lambda 延迟收尾时,不得抹掉新一代
    任务的占用期起点(否则推迟下一次僵尸检出)。"""
    import threading

    freeze_tunables(
        chroma_operation_timeout_seconds=0.3,   # 给 slow 留足运行窗口
        chroma_zombie_threshold_seconds=0.02,
    )
    release_orphan = threading.Event()

    async def scenario():
        def hang():
            release_orphan.wait(timeout=5)  # 僵尸:被隔离后仍在旧线程跑

        # hang 在 0.3s 超时,占用期(0.3)越过阈值(0.02)→ 隔离重建
        with pytest.raises(vector_chroma.ChromaZombieIsolatedError):
            await vector_chroma.run_with_chroma(hang)
        generation_after_recycle = vector_chroma._executor_generation

        def slow():
            # 新代任务进行中释放孤儿 → 孤儿 finally 与本任务并发
            release_orphan.set()
            time.sleep(0.15)
            return vector_chroma._op_started_at

        started_at = await vector_chroma.run_with_chroma(slow)

        # 无代际守卫时孤儿收尾会把 _op_started_at 抹成 None,这里必须仍是
        # slow 自己的起点
        assert started_at is not None
        assert vector_chroma._executor_generation == generation_after_recycle

    asyncio.run(scenario())
