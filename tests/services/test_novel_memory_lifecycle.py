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


class _HitSession:
    def __init__(self, fail=False):
        self.statements = []
        self.fail = fail

    async def execute(self, statement):
        if self.fail:
            raise RuntimeError("db down")
        self.statements.append(statement)


@pytest.mark.asyncio
async def test_record_recall_hits_updates_injected_atoms(monkeypatch):
    from types import SimpleNamespace

    from config import settings
    from services.novel_memory_lifecycle import record_recall_hits

    monkeypatch.setattr(settings, "ENABLE_RECALL_HIT_TRACKING", True)
    db = _HitSession()
    atom = SimpleNamespace(id=uuid.uuid4())
    duplicate = SimpleNamespace(id=atom.id)
    no_id = SimpleNamespace()

    await record_recall_hits(db, 9, [atom, duplicate, no_id])

    assert len(db.statements) == 1
    compiled = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "recall_use_count" in compiled
    assert "last_recalled_chapter" in compiled


@pytest.mark.asyncio
async def test_record_recall_hits_respects_flag_and_swallows_errors(monkeypatch):
    from types import SimpleNamespace

    from config import settings
    from services.novel_memory_lifecycle import record_recall_hits

    monkeypatch.setattr(settings, "ENABLE_RECALL_HIT_TRACKING", False)
    db = _HitSession()
    await record_recall_hits(db, 9, [SimpleNamespace(id=uuid.uuid4())])
    assert db.statements == []

    monkeypatch.setattr(settings, "ENABLE_RECALL_HIT_TRACKING", True)
    failing = _HitSession(fail=True)
    # 簿记失败必须静默：召回的 advisory 性质不允许被统计破坏
    await record_recall_hits(failing, 9, [SimpleNamespace(id=uuid.uuid4())])


def test_recall_profile_table_is_complete_per_agent():
    """召回配置单表守恒:每个角色六项配置齐全,compat 旧名与表一致。"""
    from services import novel_memory_recall as r

    required_agents = {"planner", "writer", "editor", "validator", "extractor"}
    assert set(r.AGENT_RECALL_PROFILES) == required_agents
    for name, profile in r.AGENT_RECALL_PROFILES.items():
        assert profile.budget.max_chars > 0
        assert profile.hybrid_vector_limit > 0
        assert profile.atom_types
        assert profile.scene_types
        assert profile.narrative_index_chars > 0
    # 旧名必须继续从单表派生,防止两处漂移
    assert r.RECALL_BUDGETS == {n: p.budget for n, p in r.AGENT_RECALL_PROFILES.items()}
    assert r.HYBRID_VECTOR_LIMITS == {n: p.hybrid_vector_limit for n, p in r.AGENT_RECALL_PROFILES.items()}
    assert r.HYBRID_VECTOR_SOURCES == {n: set(p.hybrid_vector_sources) for n, p in r.AGENT_RECALL_PROFILES.items()}
    assert r._AGENT_ATOM_TYPES == {n: set(p.atom_types) for n, p in r.AGENT_RECALL_PROFILES.items()}
    assert r._AGENT_SCENE_TYPES == {n: set(p.scene_types) for n, p in r.AGENT_RECALL_PROFILES.items()}


def test_narrative_index_chars_single_source():
    from services.novel_memory_recall import narrative_index_chars_for

    assert narrative_index_chars_for("planner") == 1000
    assert narrative_index_chars_for("extractor") == 600
    assert narrative_index_chars_for("unknown-agent") == 800  # 回落 writer 默认
