import uuid

import pytest
from types import SimpleNamespace
from sqlalchemy.dialects import postgresql

from services.novel_memory_recall import (
    RECALL_BUDGETS,
    format_recall_context,
    lexical_recall_score,
    merge_layered_context,
    remove_authority_duplicates,
    recall_novel_memory,
    rank_recall_items,
)
from services.novel_memory_ranking import latest_atoms_by_key, latest_scene_blocks


class _Rows:
    def all(self):
        return []


class _RecallSession:
    def __init__(self):
        self.statements = []

    async def scalars(self, statement):
        self.statements.append(statement)
        return _Rows()

    async def rollback(self):
        raise AssertionError("rollback should not be needed for a successful recall")


def test_recall_budgets_are_centralized_per_agent():
    assert RECALL_BUDGETS["planner"].max_chars > RECALL_BUDGETS["writer"].max_chars
    assert RECALL_BUDGETS["validator"].atom_limit >= RECALL_BUDGETS["writer"].atom_limit


def test_lexical_recall_prefers_query_match_over_newer_irrelevant_item():
    older_match = type(
        "Atom",
        (),
        {"statement": "林默在档案馆找到带有灰纹的封条", "source_chapter": 2, "version": 1},
    )()
    newer_unrelated = type(
        "Atom",
        (),
        {"statement": "港区的潮汐闸门暂时关闭", "source_chapter": 9, "version": 1},
    )()

    assert lexical_recall_score("档案馆 灰纹封条", older_match.statement) > lexical_recall_score(
        "档案馆 灰纹封条", newer_unrelated.statement
    )
    ranked = rank_recall_items(
        [newer_unrelated, older_match],
        "档案馆 灰纹封条",
        limit=2,
        text_getter=lambda item: item.statement,
    )
    assert ranked[0] is older_match


def test_ranking_helpers_are_available_as_http_independent_module():
    atom = type("Atom", (), {"memory_key": "state", "source_chapter": 2, "version": 1})()
    assert latest_atoms_by_key([atom]) == [atom]
    assert latest_scene_blocks([]) == []


def test_format_recall_context_has_layer_order_and_budget():
    doctrine = type("Doctrine", (), {"content": "叙事原则"})()
    scene = type("Scene", (), {"scope_type": "plotline", "scope_key": "主线", "summary": "当前冲突"})()
    atom = type("Atom", (), {"statement": "角色状态已确认", "atom_type": "character_state"})()
    due = type("Atom", (), {"statement": "伏笔即将到期", "atom_type": "foreshadowing"})()
    result = format_recall_context([doctrine], [scene], [atom], [due], 1000)
    assert result.index("项目原则") < result.index("当前场景块") < result.index("已确认记忆") < result.index("到期伏笔")
    assert len(result) <= 1000


def test_format_recall_context_labels_vector_hits_as_advisory():
    result = format_recall_context(
        [],
        [],
        [],
        [],
        1000,
        hybrid_context="- [retrieved_advisory/第2章] 档案馆的封条仍在闪烁",
    )

    assert "历史相关片段（向量建议）" in result
    assert "retrieved_advisory" in result


def test_agent_recall_filters_atoms_by_role():
    world = type("Atom", (), {"statement": "硬规则", "atom_type": "world_rule"})()
    plot = type("Atom", (), {"statement": "主线推进", "atom_type": "plot_thread"})()

    writer = format_recall_context([], [], [world, plot], [], 1000, agent_type="writer")
    planner = format_recall_context([], [], [world, plot], [], 1000, agent_type="planner")

    assert "硬规则" in writer and "主线推进" not in writer
    assert "主线推进" in planner and "硬规则" not in planner


def test_agent_recall_filters_scene_blocks_and_candidates_by_role():
    plotline = type("Scene", (), {"scope_type": "plotline", "scope_key": "主线", "summary": "主线场景"})()
    unrelated = type("Scene", (), {"scope_type": "unrelated", "scope_key": "旧资料", "summary": "不相关场景"})()
    plot_candidate = type(
        "Atom",
        (),
        {"statement": "主线可能转向港区", "atom_type": "plot_thread", "status": "candidate", "authority": "generated"},
    )()
    world_candidate = type(
        "Atom",
        (),
        {"statement": "未知世界规则", "atom_type": "world_rule", "status": "candidate", "authority": "generated"},
    )()

    planner = format_recall_context(
        [],
        [plotline, unrelated],
        [],
        [],
        2000,
        agent_type="planner",
        candidate_atoms=[plot_candidate, world_candidate],
    )

    assert "主线场景" in planner
    assert "不相关场景" not in planner
    assert "主线可能转向港区" in planner
    assert "未知世界规则" not in planner


def test_format_recall_context_keeps_latest_atom_per_memory_key():
    older = type(
        "Atom",
        (),
        {
            "memory_key": "character_state:林默",
            "statement": "林默仍在门外观察。",
            "atom_type": "character_state",
            "source_chapter": 2,
            "version": 1,
        },
    )()
    latest = type(
        "Atom",
        (),
        {
            "memory_key": "character_state:林默",
            "statement": "林默已经跨过门槛。",
            "atom_type": "character_state",
            "source_chapter": 3,
            "version": 2,
        },
    )()

    result = format_recall_context([], [], [older, latest], [], 2000)

    assert "林默已经跨过门槛" in result
    assert "林默仍在门外观察" not in result


def test_format_recall_context_keeps_latest_scene_per_scope():
    older = type(
        "Scene",
        (),
        {
            "scope_type": "plotline",
            "scope_key": "主线",
            "summary": "角色仍在门外",
            "source_chapter": 2,
            "version": 1,
        },
    )()
    latest = type(
        "Scene",
        (),
        {
            "scope_type": "plotline",
            "scope_key": "主线",
            "summary": "角色已经进入门内",
            "source_chapter": 3,
            "version": 2,
        },
    )()

    result = format_recall_context([], [older, latest], [], [], 2000, agent_type="writer")

    assert "角色已经进入门内" in result
    assert "角色仍在门外" not in result


def test_agent_memory_hint_explains_role_specific_boundary():
    from agents.prompt_hints import novel_memory_hint

    writer = novel_memory_hint("【已确认记忆】\n- 当前场景在档案馆", "writer")
    planner = novel_memory_hint("【已确认记忆】\n- 主线推进", "planner")

    assert "writer 专属召回" in writer
    assert "已接受硬事实" in writer
    assert "planner 专属召回" in planner
    assert "到期伏笔" in planner


def test_candidate_memory_is_rendered_as_a_non_fact_clue():
    candidate = type(
        "Atom",
        (),
        {
            "statement": "录音可能来自林砚",
            "atom_type": "character_state",
            "status": "candidate",
            "authority": "generated",
            "source_chapter": 2,
        },
    )()
    result = format_recall_context([], [], [], [], 1000, candidate_atoms=[candidate])
    assert "待核对记忆线索" in result
    assert "candidate/generated" in result
    assert "禁止当作事实" in result


def test_merge_layered_context_keeps_character_card_authoritative_and_deduplicates():
    result = merge_layered_context(
        '{"name": "林默", "status": "受伤"}',
        "【已确认记忆】\n- 林默\n- 第12章改变目标\n- 第12章改变目标",
        2000,
    )
    assert result.count("林默") == 1
    assert result.count("第12章改变目标") == 1
    assert "角色卡稳定事实（权威来源）" in result
    assert "以角色卡和本章大纲为准" in result


def test_merge_layered_context_handles_empty_inputs():
    assert merge_layered_context("", "", 100) == ""


def test_remove_authority_duplicates_keeps_new_memory_and_drops_repeated_fact():
    result = remove_authority_duplicates(
        '{"name":"林默","status":"受伤"}',
        "【已确认记忆】\n- [accepted/第2章] 林默\n- [accepted/第3章] 第3章改变目标",
        1000,
    )

    assert "林默" not in result
    assert "第3章改变目标" in result


@pytest.mark.asyncio
async def test_recall_uses_exact_project_branch_storyline_scope():
    db = _RecallSession()
    branch_id = uuid.uuid4()
    result = await recall_novel_memory(
        db,
        project_id=uuid.uuid4(),
        chapter_index=20,
        agent_type="writer",
        branch_id=branch_id,
        storyline_id=f"branch:{branch_id}",
    )
    assert result.context == ""
    assert len(db.statements) == 4
    sql = str(db.statements[1].compile(dialect=postgresql.dialect()))
    assert "branch_id" in sql and "storyline_id" in sql


@pytest.mark.asyncio
async def test_recall_vector_failure_keeps_database_context(monkeypatch):
    db = _RecallSession()
    atom = type(
        "Atom",
        (),
        {
            "statement": "林默在档案馆找到封条",
            "atom_type": "character_state",
            "status": "accepted",
            "source_chapter": 2,
            "version": 1,
        },
    )()

    class Rows:
        def __init__(self, values):
            self.values = values

        def all(self):
            return self.values

    async def scalars(statement):
        db.statements.append(statement)
        position = len(db.statements)
        if position == 3:
            return Rows([atom])
        return Rows([])

    db.scalars = scalars

    async def failing_query(**kwargs):
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr("services.vector_chroma.query_collection", failing_query)
    result = await recall_novel_memory(
        db,
        project_id=uuid.uuid4(),
        chapter_index=3,
        agent_type="writer",
        query_text="档案馆 封条",
        include_vector=True,
    )

    assert "林默在档案馆找到封条" in result.context
    assert "向量建议" not in result.context


@pytest.mark.asyncio
async def test_recall_renders_vector_hits_as_advisory(monkeypatch):
    db = _RecallSession()

    async def query(**kwargs):
        assert kwargs["query_texts"] == ["档案馆 封条"]
        return {
            "documents": [["档案馆的封条仍在闪烁", "旧设定不应进入分层记忆"]],
            "metadatas": [[
                {"source": "scene_block", "chapter_index": 2, "name": "主线"},
                {"source": "setting", "chapter_index": 1, "name": "旧设定"},
            ]],
            "distances": [[0.1, 0.2]],
        }

    monkeypatch.setattr("services.vector_chroma.query_collection", query)
    monkeypatch.setattr(
        "services.vector_chroma.has_collection_documents",
        lambda _name: __import__("asyncio").sleep(0, result=True),
    )
    result = await recall_novel_memory(
        db,
        project_id=uuid.uuid4(),
        chapter_index=3,
        agent_type="writer",
        query_text="档案馆 封条",
        include_vector=True,
    )

    assert "档案馆的封条仍在闪烁" in result.context
    assert "旧设定不应进入分层记忆" not in result.context
    assert "retrieved_advisory" in result.context


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
    from config import settings
    from services.novel_memory_recall import _record_recall_hits

    monkeypatch.setattr(settings, "ENABLE_RECALL_HIT_TRACKING", True)
    db = _HitSession()
    atom = SimpleNamespace(id=uuid.uuid4())
    duplicate = SimpleNamespace(id=atom.id)
    no_id = SimpleNamespace()

    await _record_recall_hits(db, 9, [atom, duplicate, no_id])

    assert len(db.statements) == 1
    compiled = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "recall_use_count" in compiled
    assert "last_recalled_chapter" in compiled


@pytest.mark.asyncio
async def test_record_recall_hits_respects_flag_and_swallows_errors(monkeypatch):
    from config import settings
    from services.novel_memory_recall import _record_recall_hits

    monkeypatch.setattr(settings, "ENABLE_RECALL_HIT_TRACKING", False)
    db = _HitSession()
    await _record_recall_hits(db, 9, [SimpleNamespace(id=uuid.uuid4())])
    assert db.statements == []

    monkeypatch.setattr(settings, "ENABLE_RECALL_HIT_TRACKING", True)
    failing = _HitSession(fail=True)
    # 簿记失败必须静默：召回的 advisory 性质不允许被统计破坏
    await _record_recall_hits(failing, 9, [SimpleNamespace(id=uuid.uuid4())])
