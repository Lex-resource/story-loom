from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from services import (
    character_branch_service,
    character_card_service,
    knowledge_query_service,
    novel_memory_service,
    outline_service,
    pipeline_commands,
    project_service,
)
from services.knowledge_constants import CHARACTER_GROUP_SUPPORTING
from services.character_context import _relationship_is_visible_at


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecuteResult(_ScalarResult):
    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None


class _IssueSession:
    def __init__(self, values):
        self.values = values
        self.commits = 0

    async def execute(self, _statement):
        return _ExecuteResult(self.values)

    async def commit(self):
        self.commits += 1


class _MemorySession:
    def __init__(self, values, atom=None, counts=None):
        self.values = list(values)
        self.atom = atom
        self.counts = counts
        self.commits = 0
        self.statements = []
        self.execute_statements = []

    async def execute(self, _statement):
        if self.counts is None:
            raise AssertionError("Unexpected execute call")
        self.execute_statements.append(_statement)
        return SimpleNamespace(
            one=lambda: SimpleNamespace(**self.counts),
            scalar_one_or_none=lambda: self.values[0] if self.values else None,
        )

    async def scalars(self, _statement):
        self.statements.append(_statement)
        return _ScalarResult(self.values)

    async def scalar(self, _statement):
        return self.atom

    async def commit(self):
        self.commits += 1


class _JobSession:
    def __init__(self, jobs):
        self.jobs = jobs
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _ExecuteResult(self.jobs)


class _PaginationSession:
    def __init__(self, values=None):
        self.values = values or []
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _ExecuteResult(self.values)


class _OutlineSession:
    def __init__(self):
        self.commits = 0

    async def execute(self, _statement):
        return _ExecuteResult([])

    async def commit(self):
        self.commits += 1


def test_outline_optimization_commits_updated_outline(monkeypatch):
    project_id = uuid.uuid4()
    novel = SimpleNamespace(
        id=project_id,
        title="测试小说",
        outline={"书名": "测试小说"},
        novel_format="long_webnovel",
    )
    session = _OutlineSession()

    async def fake_get_novel_or_raise(_db, _project_id):
        return novel

    async def fake_optimize_skeleton(_db, novel_arg, **_kwargs):
        novel_arg.outline = {"书名": novel_arg.title, "章节": []}
        return novel_arg.outline

    monkeypatch.setattr(outline_service, "get_novel_or_raise", fake_get_novel_or_raise, raising=False)
    monkeypatch.setattr(outline_service, "optimize_skeleton", fake_optimize_skeleton)

    result = asyncio.run(outline_service.optimize_outline_endpoint(session, project_id))

    assert result["outline"] == novel.outline
    assert session.commits == 1


def test_character_relationship_visibility_respects_chapter_window():
    assert _relationship_is_visible_at(
        SimpleNamespace(valid_from_chapter=3, valid_to_chapter=6), 3
    )
    assert not _relationship_is_visible_at(
        SimpleNamespace(valid_from_chapter=3, valid_to_chapter=6), 2
    )
    assert not _relationship_is_visible_at(
        SimpleNamespace(valid_from_chapter=3, valid_to_chapter=6), 7
    )
    assert _relationship_is_visible_at(
        SimpleNamespace(valid_from_chapter=None, valid_to_chapter=None), 99
    )


def test_novel_memory_service_serializes_atoms_and_commits_status_change():
    project_id = uuid.uuid4()
    atom_id = uuid.uuid4()
    atom = SimpleNamespace(
        id=atom_id,
        project_id=project_id,
        branch_id=None,
        storyline_id="main",
        source_ref="chapter:2",
        source_chapter=2,
        confidence=0.8,
        version=1,
        valid_from_chapter=2,
        valid_to_chapter=None,
        authority="generated",
        memory_key="hero.state",
        atom_type="character_state",
        statement="主角受伤",
        data={"state": "injured"},
        status="candidate",
        evidence_id=None,
    )
    session = _MemorySession([atom], atom=atom)
    response = asyncio.run(novel_memory_service.list_memory_atoms(session, project_id))
    assert response["items"] == [
        {
            "id": str(atom_id),
            "project_id": str(project_id),
            "branch_id": None,
            "storyline_id": "main",
            "source_ref": "chapter:2",
            "source_chapter": 2,
            "confidence": 0.8,
            "version": 1,
            "valid_from_chapter": 2,
            "valid_to_chapter": None,
            "authority": "generated",
            "memory_key": "hero.state",
            "atom_type": "character_state",
            "statement": "主角受伤",
            "data": {"state": "injured"},
            "status": "candidate",
            "evidence_id": None,
        }
    ]

    result = asyncio.run(
        novel_memory_service.set_memory_atom_status(
            session, project_id, atom_id, "accepted"
        )
    )
    assert result == {"id": str(atom_id), "status": "accepted"}
    assert session.commits == 1


def test_novel_memory_summary_uses_count_results():
    project_id = uuid.uuid4()
    session = _MemorySession(
        [],
        counts={"evidence": 4, "atoms": 8, "scene_blocks": 2, "doctrines": 3},
    )

    assert asyncio.run(novel_memory_service.memory_summary(session, project_id)) == {
        "evidence": 4,
        "atoms": 8,
        "scene_blocks": 2,
        "doctrines": 3,
    }


def test_novel_memory_detail_queries_are_bounded():
    project_id = uuid.uuid4()
    loaders = (
        novel_memory_service.list_memory_atoms,
        novel_memory_service.list_memory_scenes,
        novel_memory_service.list_memory_doctrines,
        novel_memory_service.list_memory_evidence,
    )

    for loader in loaders:
        session = _MemorySession([])
        kwargs = {"limit": 12, "offset": 24}
        if loader is novel_memory_service.list_memory_atoms:
            asyncio.run(loader(session, project_id, limit=12, offset=24))
        else:
            asyncio.run(loader(session, project_id, **kwargs))
        statement = session.statements[-1]
        assert statement._limit_clause.value == 12
        assert statement._offset_clause.value == 24


def test_project_job_history_queries_are_bounded_and_stably_ordered():
    project_id = uuid.uuid4()
    session = _JobSession([])

    assert asyncio.run(
        project_service.get_jobs(session, project_id, limit=12, offset=24)
    ) == []

    statement = session.statement
    assert statement._limit_clause.value == 12
    assert statement._offset_clause.value == 24
    assert len(statement._order_by_clauses) == 2


def test_character_history_queries_are_bounded_and_unbounded_internal_calls_are_preserved():
    character_id = uuid.uuid4()
    bounded_loaders = (
        (character_card_service.list_characters, (uuid.uuid4(),), {}),
        (character_card_service.list_character_states, (character_id,), {}),
        (character_card_service.list_character_changes, (character_id,), {}),
    )
    for loader, args, kwargs in bounded_loaders:
        session = _PaginationSession()
        assert asyncio.run(
            loader(session, *args, limit=12, offset=24, **kwargs)
        ) == []
        statement = session.statements[-1]
        assert statement._limit_clause.value == 12
        assert statement._offset_clause.value == 24

        unbounded_session = _PaginationSession()
        assert asyncio.run(loader(unbounded_session, *args, **kwargs)) == []
        unbounded_statement = unbounded_session.statements[-1]
        assert unbounded_statement._limit_clause is None
        assert unbounded_statement._offset_clause is None


def test_character_branch_projection_queries_are_bounded():
    project_id = uuid.uuid4()
    character_id = uuid.uuid4()
    branch_id = uuid.uuid4()
    bounded_loaders = (
        (character_branch_service.list_character_arcs, (project_id, character_id)),
        (character_branch_service.list_character_branches, (project_id, character_id)),
        (character_branch_service.list_branch_chapters, (branch_id,)),
    )
    for loader, args in bounded_loaders:
        session = _PaginationSession()
        assert asyncio.run(loader(session, *args, limit=12, offset=24)) == []
        statement = session.statements[-1]
        assert statement._limit_clause.value == 12
        assert statement._offset_clause.value == 24
        assert len(statement._order_by_clauses) >= 2


class _GraphSession:
    def __init__(self, cards, relationships, manifests):
        self.results = iter((cards, relationships, manifests))
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _ExecuteResult(next(self.results))


def test_character_graph_bounds_related_queries_to_selected_cards():
    project_id = uuid.uuid4()
    card_id = uuid.uuid4()
    card = SimpleNamespace(id=card_id, name="主角", card_data={}, importance="normal")
    session = _GraphSession([card], [], [])

    result = asyncio.run(
        knowledge_query_service.get_character_graph(
            str(project_id), session, limit=12
        )
    )

    assert result == {
        "nodes": [
            {
                "id": "主角",
                "label": "主角",
                "group": CHARACTER_GROUP_SUPPORTING,
                "title": f"主角 ({CHARACTER_GROUP_SUPPORTING})",
            }
        ],
        "edges": [],
        "details": {"主角": "暂无详细背景记录"},
    }
    assert all(statement._limit_clause.value == 12 for statement in session.statements)
    assert all(len(statement._where_criteria) >= 2 for statement in session.statements[1:])


def test_character_graph_uses_numeric_default_limit_for_internal_callers():
    project_id = uuid.uuid4()
    card = SimpleNamespace(
        id=uuid.uuid4(), name="主角", card_data={}, importance="normal"
    )
    session = _GraphSession([card], [], [])

    asyncio.run(knowledge_query_service.get_character_graph(str(project_id), session))

    assert session.statements[0]._limit_clause.value == knowledge_query_service.DEFAULT_CHARACTER_GRAPH_LIMIT


def test_experiment_params_query_reads_latest_matching_params_only():
    project_id = uuid.uuid4()
    session = _MemorySession(
        [{"experiment": {"run_id": "run-latest"}}],
        counts={"unused": 0},
    )

    assert asyncio.run(pipeline_commands.experiment_params_for_project(session, project_id)) == {
        "run_id": "run-latest"
    }
    assert len(session.execute_statements) == 1
    assert session.execute_statements[0]._limit_clause.value == 1
