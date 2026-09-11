"""worker 控制面 service 测试:取消/重试的状态流转与守卫。

分层提醒:本文件测的是 services/worker_admin_service.py(DB 部分)与
StateMachine.cancel_job;task_registry 的进程内操作另有测试。
"""
import asyncio
import uuid
from types import SimpleNamespace

import pytest

from services import worker_admin_service
from services.pipeline_types import JobStatus, NovelStatus


JOB_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()


class _AdminSession:
    def __init__(self, job, novel=None):
        self.job = job
        self.novel = novel
        self.commits = 0
        self._first_execute = True

    async def get(self, _model, _key):
        return self.job

    async def execute(self, statement):
        # 按 FROM 子句区分查询对象(Novel 的列名里也含 "chapters" 字样,
        # 所以不能只看表名字符串):Chapter 查询(validator 锚点修复)返回 None。
        sql = str(statement).lower()
        if "from chapters" in sql:
            return SimpleNamespace(scalar_one_or_none=lambda: None)
        return SimpleNamespace(scalar_one_or_none=lambda: self.novel)

    async def commit(self):
        self.commits += 1


def _job(status=JobStatus.RUNNING, step="writer", job_type="generate"):
    return SimpleNamespace(
        id=JOB_ID,
        project_id=PROJECT_ID,
        type=job_type,
        status=status,
        current_step=step,
        current_chapter=3,
        error=None,
        params={"experiment": {"a": 1}},
    )


def _novel(status=NovelStatus.GENERATING):
    return SimpleNamespace(id=PROJECT_ID, status=status)


def test_cancel_running_generate_job_pauses_novel():
    job = _job()
    novel = _novel()
    db = _AdminSession(job, novel)

    result = asyncio.run(worker_admin_service.cancel_job(db, JOB_ID))

    assert result is job
    assert job.status == JobStatus.CANCELLED
    # novel 离开 GENERATING 置 PAUSED,可从锚点恢复
    assert novel.status == NovelStatus.PAUSED
    # 不动 current_step(保 resume 锚点语义)
    assert job.current_step == "writer"
    assert db.commits == 1


def test_cancel_terminal_job_refused():
    for status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        db = _AdminSession(_job(status=status))
        assert asyncio.run(worker_admin_service.cancel_job(db, JOB_ID)) is None


def test_cancel_non_generate_job_leaves_novel_alone():
    job = _job(job_type="extraction")
    novel = _novel()
    db = _AdminSession(job, novel)

    asyncio.run(worker_admin_service.cancel_job(db, JOB_ID))

    assert job.status == JobStatus.CANCELLED
    assert novel.status == NovelStatus.GENERATING  # 未受影响


def test_cancel_missing_job_returns_none():
    db = _AdminSession(None)
    assert asyncio.run(worker_admin_service.cancel_job(db, JOB_ID)) is None


def test_retry_paused_job_resets_status_and_clears_error():
    job = _job(status=JobStatus.PAUSED, step="writer")
    job.error = "上次的错误"
    db = _AdminSession(job, _novel(status=NovelStatus.PAUSED))

    result = asyncio.run(worker_admin_service.retry_job(db, JOB_ID))

    assert result is job
    assert job.status == JobStatus.PENDING
    assert job.error is None
    assert job.current_step == "writer"
    assert db.commits == 1


def test_retry_validator_blocked_job_repairs_anchor():
    """validator 锚点的任务重试时退回 writer(与 resume 同一复位路径)。"""
    job = _job(status=JobStatus.FAILED, step="validator")
    db = _AdminSession(job, _novel(status=NovelStatus.PAUSED))

    asyncio.run(worker_admin_service.retry_job(db, JOB_ID))

    assert job.status == JobStatus.PENDING
    assert job.current_step == "writer"


def test_retry_active_or_completed_job_refused():
    for status in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.COMPLETED):
        db = _AdminSession(_job(status=status))
        assert asyncio.run(worker_admin_service.retry_job(db, JOB_ID)) is None


def test_retry_cancelled_job_is_allowed():
    job = _job(status=JobStatus.CANCELLED, step="planner")
    db = _AdminSession(job, _novel(status=NovelStatus.PAUSED))

    asyncio.run(worker_admin_service.retry_job(db, JOB_ID))

    assert job.status == JobStatus.PENDING


def test_claim_paused_toggle_roundtrip(monkeypatch, freeze_tunables):
    """开关读写走 runtime_tunables(真实 update_values,假 session)。"""
    from services import runtime_tunables_service as rts

    class _TunablesSession:
        def __init__(self):
            self.rows = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, _model, key):
            for row in self.rows:
                if row.key == key:
                    return row
            return None

        def add(self, row):
            self.rows.append(row)

        async def commit(self):
            pass

    session = _TunablesSession()
    import database

    monkeypatch.setattr(database, "async_session", lambda: session)
    rts.reset_tunables_cache_for_tests()
    try:
        values = asyncio.run(worker_admin_service.set_claim_paused(True))
        assert values["worker_claim_paused"] is True
    finally:
        rts.reset_tunables_cache_for_tests()


def test_worker_status_lists_pending_and_retryable(monkeypatch, freeze_tunables):
    """status 返回排队明细与可重试列表(供前端队列操作),错误只留摘要。"""
    import datetime

    freeze_tunables()  # 默认值,不触碰 DB

    running = SimpleNamespace(id=uuid.uuid4(), project_id=uuid.uuid4(), current_step="writer", current_chapter=2)
    pending = SimpleNamespace(id=uuid.uuid4(), project_id=uuid.uuid4(), type="generate", created_at=datetime.datetime(2026, 8, 29, 12, 0, 0))
    retryable = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        type="generate",
        status=JobStatus.FAILED,
        current_step="validator",
        current_chapter=3,
        error="第一行上下文\n最后的错误:LLM 超时",
    )

    class _StatusSession:
        """按 worker_status 的固定调用顺序分发:两次 count → running → pending → retryable。
        (SQL 参数渲染为占位符,不能按状态字面量分发。)"""

        def __init__(self):
            self._call = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, statement):
            self._call += 1
            if self._call == 1:
                return SimpleNamespace(scalar_one=lambda: 2)   # pending 计数
            if self._call == 2:
                return SimpleNamespace(scalar_one=lambda: 1)   # running 计数
            if self._call == 3:
                return SimpleNamespace(all=lambda: [running])
            if self._call == 4:
                return SimpleNamespace(all=lambda: [pending])
            return SimpleNamespace(all=lambda: [retryable])

    import database

    monkeypatch.setattr(database, "async_session", lambda: _StatusSession())

    status = asyncio.run(worker_admin_service.worker_status())

    assert status["mode"] == "in_process"
    assert status["pending_jobs"] == 2
    assert status["running_jobs"] == 1
    assert status["running_list"][0]["current_step"] == "writer"
    assert status["pending_list"][0]["type"] == "generate"
    assert status["retryable_list"][0]["status"] == "failed"
    assert status["retryable_list"][0]["error"] == "最后的错误:LLM 超时"


def test_error_snippet_takes_last_line_and_truncates():
    assert worker_admin_service._error_snippet(None) is None
    assert worker_admin_service._error_snippet("a\nb\n最后一行") == "最后一行"
    long = "x" * 200
    snippet = worker_admin_service._error_snippet(long)
    assert len(snippet) == 121 and snippet.endswith("…")
