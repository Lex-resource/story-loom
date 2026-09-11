import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from services.novel_memory_scenes import (
    aggregate_scene_block,
    build_scene_block_content_hash,
)


class _SceneSession:
    def __init__(self, block, previous=None):
        self.block = block
        self.previous = previous
        self.scalar_calls = 0
        self.statements = []
        self.added = []

    async def scalar(self, statement):
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return None  # content-hash 幂等查询
        if self.scalar_calls == 2:
            return self.previous  # 上一版本查询（diff 依据）
        if self.scalar_calls == 3:
            return None  # max(version)
        return self.block  # 插入后的回读

    async def execute(self, statement):
        self.statements.append(statement)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


def test_scene_block_hash_is_stable():
    args = {
        "summary": "城门冲突升级",
        "current_state": {"location": "城门"},
        "open_questions": ["谁在幕后"],
        "recent_changes": ["主角受伤"],
    }
    assert build_scene_block_content_hash(**args) == build_scene_block_content_hash(**args)
    assert build_scene_block_content_hash(**args) != build_scene_block_content_hash(**{**args, "summary": "冲突暂缓"})


@pytest.mark.asyncio
async def test_aggregate_scene_block_is_versioned_and_projects_summary():
    project_id = uuid.uuid4()
    block = SimpleNamespace(
        project_id=project_id,
        branch_id=None,
        storyline_id="main",
        scope_type="plotline",
        scope_key="主线冲突",
        summary="城门冲突升级",
        version=1,
        valid_from_chapter=8,
        valid_to_chapter=None,
        source_chapter=8,
    )
    db = _SceneSession(block)

    result = await aggregate_scene_block(
        db,
        project_id=project_id,
        scope_type="plotline",
        scope_key="主线冲突",
        summary="城门冲突升级",
        current_state={"location": "城门"},
        open_questions=["谁在幕后"],
        recent_changes=["主角受伤"],
        source_ref="chapter:8:scene",
        source_chapter=8,
        valid_from_chapter=8,
    )

    assert result is block
    assert len(db.statements) == 1
    assert len(db.added) == 1
    payload = db.added[0].payload
    assert payload["items"][0]["source"] == "scene_block"
    assert payload["items"][0]["metadata"]["storyline_id"] == "main"
    assert all(value is not None for value in payload["items"][0]["metadata"].values())
    assert "branch_id" not in payload["items"][0]["metadata"]
    assert "valid_to_chapter" not in payload["items"][0]["metadata"]
    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    assert "ON CONFLICT DO NOTHING" in str(compiled)


def test_build_consolidation_diff_reports_state_and_question_changes():
    from services.novel_memory_scenes import build_consolidation_diff

    previous = SimpleNamespace(
        version=3,
        source_chapter=7,
        summary="城门对峙",
        current_state={"location": "城门", "weather": "雨"},
        open_questions=["谁在幕后"],
        recent_changes=["主角受伤"],
    )
    diff = build_consolidation_diff(
        previous,
        summary="城门冲突升级",
        current_state={"location": "城门", "casualties": "守军两名"},
        open_questions=["谁在幕后", "援军何时到"],
        recent_changes=["主角受伤", "城门破损"],
        source_chapter=8,
    )
    assert diff["from_version"] == 3
    assert diff["to_chapter"] == 8
    assert diff["summary_changed"] is True
    assert diff["state_changed_keys"] == ["casualties", "weather"]
    assert diff["open_questions_added"] == ["援军何时到"]
    assert diff["open_questions_removed"] == []
    assert diff["recent_changes_appended"] == ["城门破损"]


def test_build_consolidation_diff_is_none_for_first_version():
    from services.novel_memory_scenes import build_consolidation_diff

    assert build_consolidation_diff(
        None,
        summary="开场",
        current_state={},
        open_questions=[],
        recent_changes=[],
        source_chapter=1,
    ) is None


@pytest.mark.asyncio
async def test_aggregate_scene_block_persists_consolidation_diff():
    project_id = uuid.uuid4()
    previous = SimpleNamespace(
        version=1,
        source_chapter=7,
        summary="城门对峙",
        current_state={"location": "城门"},
        open_questions=["谁在幕后"],
        recent_changes=[],
        consolidation_diff=None,
    )
    block = SimpleNamespace(
        project_id=project_id,
        branch_id=None,
        storyline_id="main",
        scope_type="plotline",
        scope_key="主线冲突",
        summary="城门冲突升级",
        version=2,
        valid_from_chapter=8,
        valid_to_chapter=None,
        source_chapter=8,
        consolidation_diff={"from_version": 1, "summary_changed": True},
    )
    db = _SceneSession(block, previous=previous)

    await aggregate_scene_block(
        db,
        project_id=project_id,
        scope_type="plotline",
        scope_key="主线冲突",
        summary="城门冲突升级",
        current_state={"location": "城门"},
        open_questions=[],
        recent_changes=["主角受伤"],
        source_ref="chapter:8:scene",
        source_chapter=8,
        valid_from_chapter=8,
    )

    # 插入语句携带 consolidation_diff 列
    compiled = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "consolidation_diff" in compiled
