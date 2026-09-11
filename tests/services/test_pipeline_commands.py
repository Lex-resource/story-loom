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

    def scalar_one_or_none(self):
        return self.values[0] if self.values else None


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


def test_resume_is_durable(monkeypatch):
    novel = SimpleNamespace(status=NovelStatus.PAUSED)
    job = SimpleNamespace(
        status=JobStatus.PAUSED,
        params={"await_outline_review": True},
        error="old error",
        current_step=None,
    )
    db = _Db()

    async def fake_lock_project(_db, _project_id):
        return novel

    async def fake_latest_job(_db, _project_id, *, lock=False):
        return job

    monkeypatch.setattr(pipeline_commands, "lock_project", fake_lock_project)
    monkeypatch.setattr(pipeline_commands, "latest_generate_job", fake_latest_job)

    resumed = asyncio.run(pipeline_commands.resume_project(db, uuid.uuid4()))

    assert resumed is job
    assert novel.status == NovelStatus.GENERATING
    assert job.status == JobStatus.PENDING
    assert job.params == {}
    assert job.error is None
    assert db.commits == 1


def test_resume_completed_step_job_preserves_experiment_metadata(monkeypatch):
    novel = SimpleNamespace(status=NovelStatus.PAUSED)
    job = SimpleNamespace(
        status=JobStatus.COMPLETED,
        params={
            "experiment": {
                "run_id": "run-v6",
                "prompt_version": "V6",
                "variant": "continuity",
                "root_dir": "data/research_runs",
            },
            "remaining_chapters": 0,
        },
        error=None,
        current_step="planner",
    )
    db = _Db()

    async def fake_lock_project(_db, _project_id):
        return novel

    async def fake_latest_job(_db, _project_id, *, lock=False):
        return job

    monkeypatch.setattr(pipeline_commands, "lock_project", fake_lock_project)
    monkeypatch.setattr(pipeline_commands, "latest_generate_job", fake_latest_job)

    resumed = asyncio.run(pipeline_commands.resume_project(db, uuid.uuid4()))

    assert resumed is db.added[0]
    assert resumed.params == {
        "experiment": job.params["experiment"],
        "remaining_chapters": 1,
    }
    assert resumed.status == JobStatus.PENDING
    assert novel.status == NovelStatus.GENERATING


def test_resume_falls_back_to_older_experiment_job(monkeypatch):
    novel = SimpleNamespace(status=NovelStatus.PAUSED)
    latest_job = SimpleNamespace(
        status=JobStatus.COMPLETED,
        params={"use_existing_outline": True},
        error=None,
        current_step="planner",
    )
    older_job = SimpleNamespace(
        status=JobStatus.PAUSED,
        params={
            "experiment": {
                "run_id": "run-v9",
                "prompt_version": "V9",
                "variant": "temporal-gate",
                "root_dir": "data/research_runs",
            }
        },
        error=None,
        current_step="validator",
    )
    db = _Db([latest_job, older_job])

    async def fake_lock_project(_db, _project_id):
        return novel

    async def fake_latest_job(_db, _project_id, *, lock=False):
        return latest_job

    monkeypatch.setattr(pipeline_commands, "lock_project", fake_lock_project)
    monkeypatch.setattr(pipeline_commands, "latest_generate_job", fake_latest_job)

    resumed = asyncio.run(pipeline_commands.resume_project(db, uuid.uuid4()))

    assert resumed is db.added[0]
    assert resumed.params == {
        "experiment": older_job.params["experiment"],
        "remaining_chapters": 1,
    }


def test_resume_paused_job_recovers_older_experiment_metadata(monkeypatch):
    novel = SimpleNamespace(status=NovelStatus.PAUSED)
    latest_job = SimpleNamespace(
        status=JobStatus.PAUSED,
        params={"use_existing_outline": True},
        error=None,
        current_step="editor",
    )
    older_job = SimpleNamespace(
        status=JobStatus.COMPLETED,
        params={
            "experiment": {
                "run_id": "run-v9",
                "prompt_version": "V9",
                "variant": "temporal-gate",
            }
        },
        error=None,
        current_step="planner",
    )
    db = _Db([latest_job, older_job])

    async def fake_lock_project(_db, _project_id):
        return novel

    async def fake_latest_job(_db, _project_id, *, lock=False):
        return latest_job

    monkeypatch.setattr(pipeline_commands, "lock_project", fake_lock_project)
    monkeypatch.setattr(pipeline_commands, "latest_generate_job", fake_latest_job)

    resumed = asyncio.run(pipeline_commands.resume_project(db, uuid.uuid4()))

    assert resumed is latest_job
    assert resumed.params["experiment"] == older_job.params["experiment"]


def test_resume_validator_block_returns_to_writer(monkeypatch):
    novel = SimpleNamespace(status=NovelStatus.PAUSED)
    chapter = SimpleNamespace(
        novel_id=uuid.uuid4(),
        chapter_index=1,
        rewrite_count=3,
    )
    job = SimpleNamespace(
        status=JobStatus.PAUSED,
        params={"experiment": {"run_id": "run-v14"}},
        error=None,
        current_step="validator",
        current_chapter=1,
    )
    db = _Db([chapter])

    async def fake_lock_project(_db, _project_id):
        return novel

    async def fake_latest_job(_db, _project_id, *, lock=False):
        return job

    monkeypatch.setattr(pipeline_commands, "lock_project", fake_lock_project)
    monkeypatch.setattr(pipeline_commands, "latest_generate_job", fake_latest_job)

    resumed = asyncio.run(pipeline_commands.resume_project(db, uuid.uuid4()))

    assert resumed is job
    assert resumed.current_step == "writer"
    assert resumed.status == JobStatus.PENDING
    assert chapter.rewrite_count == 2
