import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

from services import character_branch_service
from services import character_branch_generation
from services import worker_admin_service
from services.pipeline_types import JobStatus


BRANCH_ID = uuid.uuid4()
CHARACTER_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return SimpleNamespace(all=lambda: self.value)


class _BranchSession:
    def __init__(self, branch, chapter):
        self.branch = branch
        self.chapter = chapter

    async def execute(self, statement):
        sql = str(statement).lower()
        if "character_branch_chapters" in sql:
            return _Result(self.chapter)
        if "character_branches" in sql:
            return _Result(self.branch)
        raise AssertionError(f"unexpected statement: {statement}")


def _branch(status="generating"):
    return SimpleNamespace(
        id=BRANCH_ID,
        project_id=PROJECT_ID,
        character_id=CHARACTER_ID,
        status=status,
        current_chapter_index=1,
        error=None,
    )


def test_stopping_branch_job_repairs_current_chapter_for_resume():
    branch = _branch()
    chapter = SimpleNamespace(status="generating", error=None)
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        params={"branch_id": str(BRANCH_ID)},
    )

    asyncio.run(
        character_branch_service.stop_character_branch_job(
            _BranchSession(branch, chapter), job
        )
    )

    assert branch.status == "draft"
    assert chapter.status == "draft"
    assert "取消" in branch.error
    assert chapter.error == branch.error


def test_branch_checkpoint_observes_durable_cancellation():
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        status=JobStatus.RUNNING,
    )

    class _CancelledSession:
        async def execute(self, _statement):
            return _Result(JobStatus.CANCELLED)

    try:
        asyncio.run(
            character_branch_generation._branch_checkpoint(
                _CancelledSession(), job, BRANCH_ID, CHARACTER_ID, lock=False
            )
        )
    except character_branch_generation.BranchJobAborted as exc:
        assert exc.status == JobStatus.CANCELLED
    else:
        raise AssertionError("cancelled branch job must stop at a checkpoint")
    assert job.status == JobStatus.CANCELLED


def test_cancel_branch_job_does_not_pause_novel(monkeypatch):
    branch = _branch()
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        type="character_branch",
        status=JobStatus.RUNNING,
        current_step="branch",
        current_chapter=None,
        error=None,
        params={"branch_id": str(BRANCH_ID)},
    )
    novel = SimpleNamespace(status="generating")

    async def fake_stop(_db, _job):
        branch.status = "draft"
        return branch

    monkeypatch.setattr(
        "services.character_branch_service.stop_character_branch_job", fake_stop
    )
    db = SimpleNamespace(
        job=job,
        async_get=lambda *_args: job,
        get=None,
    )

    async def get(_model, _key):
        return job

    async def commit():
        return None

    db.get = get
    db.commit = commit

    result = asyncio.run(worker_admin_service.cancel_job(db, job.id))

    assert result is job
    assert job.status == JobStatus.CANCELLED
    assert novel.status == "generating"


def test_stale_branch_cleanup_repairs_branch_without_pausing_project(monkeypatch):
    from worker_support import orphan_cleaner

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    job = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        type="character_branch",
        status=JobStatus.RUNNING,
        updated_at=now - timedelta(hours=1),
        created_at=now - timedelta(hours=2),
        current_step="branch",
        current_chapter=None,
    )
    novel = SimpleNamespace(status="generating")
    calls = []

    class _Db:
        async def execute(self, statement):
            if "from novels" in str(statement).lower():
                return _Result(novel)
            return _Result([job])

        async def commit(self):
            return None

    class _Factory:
        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, *_args):
            return False

    async def fake_recover(_db, _job, *, reason):
        calls.append(reason)

    monkeypatch.setattr(orphan_cleaner, "async_session", lambda: _Factory())
    monkeypatch.setattr(orphan_cleaner, "is_active", lambda _job_id: False)
    monkeypatch.setattr(orphan_cleaner, "get_value", lambda _key: asyncio.sleep(0, result=1))
    monkeypatch.setattr(orphan_cleaner, "recover_character_branch_job", fake_recover)
    monkeypatch.setattr(orphan_cleaner, "append_job_error", lambda *_args, **_kwargs: None)

    asyncio.run(orphan_cleaner.cleanup_orphaned_jobs())

    assert job.status == JobStatus.FAILED
    assert calls
    assert novel.status == "generating"
