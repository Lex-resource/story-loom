import asyncio
import uuid
from types import SimpleNamespace

from services import pipeline_service
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
    def __init__(self, results):
        self.results = list(results)
        self.commits = 0

    async def execute(self, _statement):
        return _Result(self.results.pop(0))

    async def commit(self):
        self.commits += 1


def test_rewrite_recovers_experiment_from_older_job():
    project_id = uuid.uuid4()
    experiment = {
        "run_id": "run-v9",
        "prompt_version": "V9",
        "variant": "temporal-gate",
    }
    chapter = SimpleNamespace(
        chapter_index=5,
        status="draft",
        pipeline_step="editor",
        draft_content="draft",
        edited_content="edited",
        content="content",
        validator_result={},
        error=None,
        rewrite_count=0,
        outline={"title": "chapter"},
    )
    latest_job = SimpleNamespace(
        project_id=project_id,
        type="generate",
        status=JobStatus.PAUSED,
        params={"use_existing_outline": True},
        error=None,
        current_step="validator",
        current_chapter=5,
    )
    older_job = SimpleNamespace(
        project_id=project_id,
        type="generate",
        status=JobStatus.COMPLETED,
        params={"experiment": experiment},
        error=None,
        current_step="planner",
        current_chapter=5,
    )
    novel = SimpleNamespace(status=NovelStatus.PAUSED)
    db = _Db([[chapter], [latest_job, older_job], [novel]])

    result = asyncio.run(
        pipeline_service.rewrite(
            db,
            project_id,
            use_existing_outline=True,
            chapter_index=5,
        )
    )

    assert result == {"status": "retrying"}
    assert latest_job.params["experiment"] == experiment
    assert latest_job.current_step == "writer"
    assert latest_job.status == JobStatus.PENDING
    assert novel.status == NovelStatus.GENERATING
    assert db.commits == 1
