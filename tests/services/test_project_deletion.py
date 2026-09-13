from __future__ import annotations

import asyncio
import uuid

from services import project_deletion
from services.chapter_deletion import ChapterDeletionError, assert_chapter_deletable


class _ScalarResult:
    def __init__(self, values):
        self.values = list(values)

    def all(self):
        return list(self.values)


class _ExecuteResult:
    def __init__(self, values=()):
        self.values = list(values)

    def scalars(self):
        return _ScalarResult(self.values)


class _CleanupSession:
    def __init__(self, active_ids):
        self.active_ids = active_ids
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _ExecuteResult(self.active_ids)
        return _ExecuteResult()


def test_cancel_active_project_jobs_marks_pending_and_running_jobs_cancelled():
    project_id = uuid.uuid4()
    job_id = uuid.uuid4()
    session = _CleanupSession([job_id])

    result = asyncio.run(project_deletion.cancel_active_project_jobs(session, project_id))

    assert result == [job_id]
    assert len(session.statements) == 2
    assert session.statements[1].compile().params["status"] == "cancelled"


def test_delete_project_projections_removes_project_dir_and_all_namespaces(
    monkeypatch, tmp_path
):
    project_id = uuid.uuid4()
    branch_id = uuid.uuid4()
    project_dir = tmp_path / str(project_id)
    project_dir.mkdir()
    (project_dir / "current.md").write_text("data", encoding="utf-8")
    deleted = []

    async def fake_delete_collection(name):
        deleted.append(name)

    monkeypatch.setattr(
        "services.project_deletion.get_project_dir",  # 打在使用处
        lambda _project_id: project_dir,
    )
    monkeypatch.setattr("services.project_deletion.delete_collection", fake_delete_collection)  # 补丁打在使用处(模块导入期绑定)

    errors = asyncio.run(project_deletion.delete_project_projections(project_id, [branch_id]))

    assert errors == []
    assert deleted == [f"project_{project_id}", f"character_branch_{branch_id}"]
    assert not project_dir.exists()


class _ScalarSession:
    def __init__(self, values):
        self.values = iter(values)

    async def scalar(self, _statement):
        return next(self.values)


def test_chapter_deletion_only_allows_last_chapter_without_active_job():
    project_id = uuid.uuid4()

    asyncio.run(assert_chapter_deletable(_ScalarSession([3, None, None]), project_id, 3))
    try:
        asyncio.run(assert_chapter_deletable(_ScalarSession([3]), project_id, 2))
    except ChapterDeletionError as error:
        assert "最后一章" in str(error)
    else:
        raise AssertionError("middle chapter deletion should be rejected")
