import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from services.novel_memory_scenes import (
    aggregate_scene_block,
    build_scene_block_content_hash,
)


class _SceneSession:
    def __init__(self, block):
        self.block = block
        self.scalar_calls = 0
        self.statements = []
        self.added = []

    async def scalar(self, statement):
        self.scalar_calls += 1
        if self.scalar_calls in (1, 2):
            return None
        return self.block

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
