import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from services.novel_memory_lifecycle import sweep_stale_atom_candidates


class _SweepSession:
    def __init__(self, rowcount=2):
        self.rowcount = rowcount
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(rowcount=self.rowcount)


@pytest.mark.asyncio
async def test_sweep_only_touches_stale_candidates():
    db = _SweepSession(rowcount=3)
    project_id = uuid.uuid4()

    swept = await sweep_stale_atom_candidates(
        db,
        project_id=project_id,
        current_chapter=30,
        idle_chapters=12,
    )

    assert swept == 3
    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    assert "UPDATE novel_memory_atoms" in str(compiled)
    assert "coalesce" in str(compiled)
    # 只降级 candidate，绝不触碰 accepted（伏笔到期由 valid_to_chapter 驱动）
    assert compiled.params["status"] == "superseded"
    assert compiled.params["status_1"] == "candidate"


@pytest.mark.asyncio
async def test_sweep_idle_chapters_floor_is_one():
    db = _SweepSession()
    project_id = uuid.uuid4()

    await sweep_stale_atom_candidates(
        db,
        project_id=project_id,
        current_chapter=5,
        idle_chapters=0,
    )

    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    # idle=0 被钳到 1：current - 1 = 4
    assert compiled.params["coalesce_1"] == 4
