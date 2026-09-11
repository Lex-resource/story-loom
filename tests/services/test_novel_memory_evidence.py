import uuid

import pytest
from sqlalchemy.dialects import postgresql

from models.novel_memory import NovelMemoryEvidence
from services.novel_memory_evidence import (
    build_evidence_content_hash,
    capture_branch_generation_evidence,
    capture_chapter_extractor_evidence,
    chapter_evidence_source_ref,
    list_evidence,
)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value or []


class _Session:
    def __init__(self, evidence):
        self.evidence = evidence
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(None if len(self.statements) == 1 else self.evidence)


class _ReadSession:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result([])


def test_evidence_hash_is_stable_and_tracks_both_inputs():
    first = build_evidence_content_hash("正文", {"patches": []})
    equivalent = build_evidence_content_hash("正文", {"patches": []})
    changed_source = build_evidence_content_hash("正文2", {"patches": []})
    changed_output = build_evidence_content_hash("正文", {"patches": [{"name": "林"}]})

    assert first == equivalent
    assert first != changed_source
    assert first != changed_output
    assert len(first) == 64


@pytest.mark.asyncio
async def test_chapter_capture_is_append_only_and_idempotent_shape():
    project_id = uuid.uuid4()
    evidence = NovelMemoryEvidence(id=uuid.uuid4(), project_id=project_id)
    db = _Session(evidence)

    returned = await capture_chapter_extractor_evidence(
        db,
        project_id=project_id,
        chapter_index=7,
        chapter_content="章节正文",
        extractor_output={"patches": []},
    )

    assert returned is evidence
    assert len(db.statements) == 2
    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    insert_sql = str(compiled)
    assert "ON CONFLICT DO NOTHING" in insert_sql
    assert chapter_evidence_source_ref(7) == "chapter:7:extractor"


@pytest.mark.asyncio
async def test_branch_capture_keeps_branch_and_storyline_scope():
    project_id = uuid.uuid4()
    branch_id = uuid.uuid4()
    evidence = NovelMemoryEvidence(id=uuid.uuid4(), project_id=project_id)
    db = _Session(evidence)

    await capture_branch_generation_evidence(
        db,
        project_id=project_id,
        branch_id=branch_id,
        storyline_id=f"branch:{branch_id}",
        chapter_index=2,
        chapter_content="支线正文",
        generation_data={"title": "支线"},
    )

    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    insert_sql = str(compiled)
    params = compiled.params
    assert "branch_generation" in params.values()
    assert any(str(branch_id) == str(value) for value in params.values())
    assert "ON CONFLICT DO NOTHING" in insert_sql


@pytest.mark.asyncio
async def test_list_evidence_filters_to_exact_branch_namespace():
    project_id = uuid.uuid4()
    branch_id = uuid.uuid4()
    db = _ReadSession()

    result = await list_evidence(
        db,
        project_id=project_id,
        branch_id=branch_id,
        storyline_id=f"branch:{branch_id}",
    )

    assert result == []
    sql = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert 'branch_id = ' in sql
    assert 'storyline_id = ' in sql
