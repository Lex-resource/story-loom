import asyncio
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from services.novel_constants import JOB_TYPE_GENERATE
from services.pipeline_types import JobStatus, NovelStatus
from worker_support import orchestrator


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Session:
    def __init__(self, rows):
        self.rows = rows

    def begin(self):
        return _Transaction()

    async def execute(self, statement):
        return SimpleNamespace(all=lambda: self.rows)


class _SessionFactory:
    def __init__(self, rows):
        self.session = _Session(rows)

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_claim_pending_jobs_transitions_only_eligible_rows(monkeypatch):
    eligible = SimpleNamespace(id="job-1", type=JOB_TYPE_GENERATE, status=JobStatus.PENDING)
    paused_project = SimpleNamespace(id="job-2", type=JOB_TYPE_GENERATE, status=JobStatus.PENDING)
    factory = _SessionFactory([
        (eligible, NovelStatus.GENERATING),
        (paused_project, NovelStatus.PAUSED),
    ])
    monkeypatch.setattr(orchestrator, "async_session", lambda: factory)

    claimed = asyncio.run(orchestrator.claim_pending_jobs(2))

    assert claimed == ["job-1"]
    assert eligible.status == JobStatus.RUNNING
    assert paused_project.status == JobStatus.PENDING


def test_claim_pending_jobs_respects_capacity_limit(monkeypatch):
    first = SimpleNamespace(id="job-1", type=JOB_TYPE_GENERATE, status=JobStatus.PENDING)
    second = SimpleNamespace(id="job-2", type=JOB_TYPE_GENERATE, status=JobStatus.PENDING)
    factory = _SessionFactory([
        (first, NovelStatus.GENERATING),
        (second, NovelStatus.GENERATING),
    ])
    monkeypatch.setattr(orchestrator, "async_session", lambda: factory)

    claimed = asyncio.run(orchestrator.claim_pending_jobs(1))

    assert claimed == ["job-1"]
    assert first.status == JobStatus.RUNNING
    assert second.status == JobStatus.PENDING


def test_claim_paused_returns_empty_without_touching_db(monkeypatch, freeze_tunables):
    """全局暂停领取:开关开启时直接返回空,连 DB 查询都不发。

    在跑任务继续到检查点 —— 暂停语义是"不领新任务",不是杀任务。
    """
    freeze_tunables(worker_claim_paused=True)

    def _boom():
        raise AssertionError("paused claim must not query the DB")

    monkeypatch.setattr(orchestrator, "async_session", _boom)

    claimed = asyncio.run(orchestrator.claim_pending_jobs(2))

    assert claimed == []


def test_claim_pending_jobs_fails_unknown_job_types(monkeypatch):
    unknown = SimpleNamespace(id="job-unknown", type="future_job", status=JobStatus.PENDING)
    factory = _SessionFactory([(unknown, NovelStatus.GENERATING)])
    monkeypatch.setattr(orchestrator, "async_session", lambda: factory)

    claimed = asyncio.run(orchestrator.claim_pending_jobs(1))

    assert claimed == []
    assert unknown.status == JobStatus.FAILED
    assert json.loads(unknown.error)["error"] == "Unsupported job type: future_job"
