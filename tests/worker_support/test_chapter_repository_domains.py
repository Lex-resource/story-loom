"""chapter_repository 域分派测试:主线默认不变,支线域走 CharacterBranchChapter。"""
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from core.chapter_domain import ChapterDomain
from worker_support import chapter_repository as repo


class _CaptureSession:
    def __init__(self, scalar_result=None, execute_result=None):
        self.scalar_result = scalar_result
        self.execute_result = execute_result
        self.statements = []
        self.added = []

    async def scalar(self, statement):
        self.statements.append(("scalar", statement))
        return self.scalar_result

    async def execute(self, statement):
        self.statements.append(("execute", statement))
        return SimpleNamespace(scalar_one_or_none=lambda: self.execute_result)

    def add(self, value):
        self.added.append(value)


def test_mainline_default_unchanged_when_domain_is_none():
    db = _CaptureSession(execute_result=None)
    import asyncio

    row = asyncio.run(
        repo.get_chapter_by_index(db, uuid.uuid4(), 3, domain=None)
    )
    assert row is None
    compiled = str(db.statements[0][1].compile(dialect=postgresql.dialect()))
    assert "chapters" in compiled
    assert "character_branch_chapters" not in compiled


def test_branch_domain_reads_branch_chapter_table():
    db = _CaptureSession(execute_result=None)
    domain = ChapterDomain(project_id=uuid.uuid4(), branch_id=uuid.uuid4())
    import asyncio

    asyncio.run(repo.get_chapter_by_index(db, domain.project_id, 3, domain=domain))
    compiled = str(db.statements[0][1].compile(dialect=postgresql.dialect()))
    assert "character_branch_chapters" in compiled
    assert "branch_id" in compiled


def test_branch_prepare_creates_branch_chapter_with_branch_status():
    from core.character_vocab import CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT

    db = _CaptureSession()
    domain = ChapterDomain(
        project_id=uuid.uuid4(), branch_id=uuid.uuid4(), anchor_main_chapter=28
    )
    import asyncio

    chapter = asyncio.run(
        repo.prepare_chapter_for_step(db, None, domain.project_id, 1, "planner", domain=domain)
    )
    assert chapter.branch_id == domain.branch_id
    assert chapter.anchor_main_chapter == 28
    assert chapter.status == CHARACTER_BRANCH_CHAPTER_STATUS_DRAFT


def test_branch_raw_issues_are_skipped():
    db = _CaptureSession()
    domain = ChapterDomain(project_id=uuid.uuid4(), branch_id=uuid.uuid4())
    import asyncio

    asyncio.run(
        repo.save_editor_raw_issues(
            db, domain.project_id, 1, [{"category": "x", "description": "y"}], domain=domain
        )
    )
    assert db.added == []  # RawIssue 是主线审核面,支线域不写
