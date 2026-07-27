import asyncio
import uuid
from types import SimpleNamespace

from services import pipeline_commands
from services.pipeline_types import JobStatus, NovelStatus


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _Result:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return _Scalars(self.values)


class _Db:
    def __init__(self, values=()):
        self.values = values
        self.commits = 0
        self.added = []

    async def execute(self, _statement):
        return _Result(self.values)

    async def commit(self):
        self.commits += 1

    def add(self, value):
        self.added.append(value)


def test_pause_project_updates_jobs_and_project(monkeypatch):
    novel = SimpleNamespace(status=NovelStatus.GENERATING)
    jobs = [SimpleNamespace(status=JobStatus.RUNNING), SimpleNamespace(status=JobStatus.PENDING)]
    db = _Db(jobs)

    async def fake_lock_project(_db, _project_id):
        return novel

    monkeypatch.setattr(pipeline_commands, "lock_project", fake_lock_project)
    asyncio.run(pipeline_commands.pause_project(db, uuid.uuid4()))

    assert novel.status == NovelStatus.PAUSED
    assert [job.status for job in jobs] == [JobStatus.PAUSED, JobStatus.PAUSED]
    assert db.commits == 1


def test_resume_and_intervention_are_durable(monkeypatch):
    novel = SimpleNamespace(status=NovelStatus.PAUSED)
    job = SimpleNamespace(
        status=JobStatus.PAUSED,
        params={"await_outline_review": True},
        error="old error",
        current_step=None,
        intervention_prompt=None,
    )
    db = _Db()

    async def fake_lock_project(_db, _project_id):
        return novel

    async def fake_latest_job(_db, _project_id, *, lock=False):
        return job

    monkeypatch.setattr(pipeline_commands, "lock_project", fake_lock_project)
    monkeypatch.setattr(pipeline_commands, "latest_generate_job", fake_latest_job)

    resumed = asyncio.run(pipeline_commands.resume_project(db, uuid.uuid4()))
    intervened = asyncio.run(pipeline_commands.set_intervention_prompt(db, uuid.uuid4(), "  keep the clue  "))

    assert resumed is job and intervened is job
    assert novel.status == NovelStatus.GENERATING
    assert job.status == JobStatus.PENDING
    assert job.params == {}
    assert job.error is None
    assert job.intervention_prompt == "keep the clue"
    assert db.commits == 2
