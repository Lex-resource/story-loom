"""S11 回归测试：outbox DONE 行分批短事务删除。

无 LIMIT 的整表 DELETE 在存量大的首跑会形成长事务；必须按
vector_outbox_purge_batch（runtime_tunables）分批循环，每批独立提交，异常时返回已删总数。
"""
import asyncio
from types import SimpleNamespace

import pytest

from worker_support import vector_outbox_worker


PURGE_BATCH = 500  # 与 runtime_tunables 的 vector_outbox_purge_batch 默认值一致


@pytest.fixture(autouse=True)
def _frozen_tunables(freeze_tunables):
    freeze_tunables(vector_outbox_purge_batch=PURGE_BATCH)
    yield


class _PurgeSession:
    def __init__(self, rowcounts):
        self.rowcounts = list(rowcounts)
        self.delete_calls = 0
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, statement):
        self.delete_calls += 1
        rowcount = self.rowcounts.pop(0) if self.rowcounts else 0
        return SimpleNamespace(rowcount=rowcount)

    async def commit(self):
        self.commits += 1


def test_batches_until_short_batch(monkeypatch):
    session = _PurgeSession([PURGE_BATCH, 120])
    monkeypatch.setattr(vector_outbox_worker, "async_session", lambda: session)

    total = asyncio.run(vector_outbox_worker.cleanup_done_outboxes())

    assert total == PURGE_BATCH + 120
    assert session.delete_calls == 2
    assert session.commits == 2


def test_no_rows_single_short_batch(monkeypatch):
    session = _PurgeSession([0])
    monkeypatch.setattr(vector_outbox_worker, "async_session", lambda: session)

    total = asyncio.run(vector_outbox_worker.cleanup_done_outboxes())

    assert total == 0
    assert session.delete_calls == 1
    assert session.commits == 1


def test_error_returns_partial_total(monkeypatch):
    session = _PurgeSession([PURGE_BATCH])
    original_execute = session.execute
    calls = {"n": 0}

    async def execute(statement):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("db gone")
        return await original_execute(statement)

    session.execute = execute
    monkeypatch.setattr(vector_outbox_worker, "async_session", lambda: session)

    total = asyncio.run(vector_outbox_worker.cleanup_done_outboxes())

    assert total == PURGE_BATCH
