from types import SimpleNamespace
from uuid import uuid4

import pytest

from agents.base import LLMJSONParsingError
from services.pipeline_types import JobStatus, NovelStatus
from worker_support import json_error_recovery as recovery


class _DB:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class _Events:
    def __init__(self):
        self.messages = []

    async def status(self, step, chapter_index, message):
        self.messages.append((step, chapter_index, message))


def _editor_schema_error():
    validation_error = SimpleNamespace(title="EditorShortFormResponse")
    return LLMJSONParsingError(
        "Schema validation failed",
        raw_response='{"evaluations": {}}',
        validation_error=validation_error,
    )


@pytest.mark.asyncio
async def test_editor_schema_error_schedules_writer_rewrite_instead_of_force_save(monkeypatch):
    db = _DB()
    job = SimpleNamespace(
        status=JobStatus.RUNNING,
        current_step="editor",
        current_chapter=1,
        error=None,
    )
    novel = SimpleNamespace(id=uuid4(), status=NovelStatus.GENERATING)
    chapter = SimpleNamespace(
        status="draft",
        pipeline_step="editing",
        draft_content="可用初稿",
        edited_content="可用修订稿",
        content=None,
        error=None,
    )
    events = _Events()
    called = {}

    async def fake_schedule(*args):
        called["scheduled"] = True

    async def fake_get_or_create(*args, **kwargs):
        return chapter

    monkeypatch.setattr(recovery, "get_or_create_chapter", fake_get_or_create)
    monkeypatch.setattr(recovery, "_schedule_editor_schema_rewrite", fake_schedule)

    result = await recovery.handle_json_parsing_error(
        db, job, novel, 1, 3, _editor_schema_error(), events
    )

    assert result == recovery.JSONErrorRecoveryOutcome.RETRY
    assert called == {"scheduled": True}
    assert db.commits == 0


@pytest.mark.asyncio
async def test_editor_schema_error_does_not_set_auto_force_saved(monkeypatch):
    db = _DB()
    job = SimpleNamespace(
        status=JobStatus.RUNNING,
        current_step="editor",
        current_chapter=1,
        error=None,
    )
    novel = SimpleNamespace(id=uuid4(), status=NovelStatus.GENERATING)
    chapter = SimpleNamespace(
        status="draft",
        pipeline_step="editing",
        draft_content="可用初稿",
        edited_content="可用修订稿",
        content=None,
        error=None,
    )
    events = _Events()

    async def fake_schedule(db, job, novel, chapter, chapter_index, error, events):
        chapter.error = '{"auto_rewrite": true}'

    async def fake_get_or_create(*args, **kwargs):
        return chapter

    monkeypatch.setattr(recovery, "get_or_create_chapter", fake_get_or_create)
    monkeypatch.setattr(recovery, "_schedule_editor_schema_rewrite", fake_schedule)

    result = await recovery.handle_json_parsing_error(
        db, job, novel, 1, 3, _editor_schema_error(), events
    )

    assert result == recovery.JSONErrorRecoveryOutcome.RETRY
    assert "auto_force_saved" not in chapter.error
