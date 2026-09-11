"""S17 回归测试：批量生成循环每章开始前清空 identity map。

长命批量任务复用一个 AsyncSession，expire_on_commit=False 下 commit 不清
identity map，已加载章节/记忆对象会随章节数线性累积。循环必须每章开始前
expunge_all 并把 job/novel 重新 merge 回 session。
"""
import asyncio
from types import SimpleNamespace

import pytest

from services.novel_constants import JOB_TYPE_GENERATE
from services.pipeline_types import JobStatus, NovelStatus
from worker_support import generation_job_batch_runner as batch_runner
from worker_support.generation_bootstrap import BootstrapOutcome


class _MemorySession:
    def __init__(self):
        self.expunge_calls = 0
        self.merged = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        return None

    async def execute(self, statement):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: []),
            scalar_one_or_none=lambda: None,
            all=lambda: [],
        )

    def expunge_all(self):
        self.expunge_calls += 1

    async def merge(self, obj):
        self.merged.append(obj)
        return obj


def _fake_async(value):
    async def _fn(*args, **kwargs):
        return value

    return _fn


def _fake_seq_async(values):
    iterator = iter(values)

    async def _fn(*args, **kwargs):
        return next(iterator)

    return _fn


@pytest.fixture
def job_and_novel():
    job = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        type=JOB_TYPE_GENERATE,
        status="running",
        params={"batch_size": 2},
        current_step="writer",
        current_chapter=1,
        error=None,
    )
    novel = SimpleNamespace(
        id="22222222-2222-2222-2222-222222222222",
        status=NovelStatus.GENERATING,
        target_chapters=10,
    )
    return job, novel


def test_loop_expunges_and_remerges_each_chapter(monkeypatch, job_and_novel):
    job, novel = job_and_novel
    session = _MemorySession()

    monkeypatch.setattr(batch_runner, "get_novel_for_job", _fake_async(novel))
    monkeypatch.setattr(
        batch_runner, "bootstrap_skeleton_outline", _fake_async(BootstrapOutcome.CONTINUE)
    )
    monkeypatch.setattr(
        batch_runner, "find_next_chapter_for_job", _fake_seq_async([1, 2])
    )
    monkeypatch.setattr(batch_runner, "process_single_chapter", _fake_async(None))
    monkeypatch.setattr(batch_runner, "reset_job_for_next_chapter", _fake_async(None))
    monkeypatch.setattr(batch_runner, "decrement_remaining_chapters", _fake_async(None))
    monkeypatch.setattr(
        batch_runner, "update_novel_status_on_finished", _fake_async(None)
    )

    asyncio.run(batch_runner.process_generate_job(session, job))

    # 两章 → 两次清场；每次清场后 job/novel 都重新挂回
    assert session.expunge_calls == 2
    assert session.merged.count(job) == 2
    assert session.merged.count(novel) == 2
    assert job.status == JobStatus.COMPLETED
