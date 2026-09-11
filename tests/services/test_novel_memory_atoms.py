import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from services.knowledge_patch_models import KnowledgePatch, KnowledgePatchSet
from services.novel_memory_atoms import (
    accept_atom_candidates,
    build_atom_candidate_hash,
    reject_atom_candidate,
    record_patch_atoms,
    supersede_atom,
    sync_world_rule_doctrines,
)


class _AtomSession:
    def __init__(self):
        self.scalar_calls = 0
        self.statements = []
        self.atom = SimpleNamespace(id=uuid.uuid4(), candidate_hash="hash")

    async def scalar(self, statement):
        self.scalar_calls += 1
        if self.scalar_calls % 2 == 1:
            return None
        return self.atom

    async def execute(self, statement):
        self.statements.append(statement)


def _patch():
    return KnowledgePatch(
        category="foreshadowing",
        operation="upsert",
        name="黑匣子",
        data={"description": "尚未揭开的来源", "confidence": 0.8},
    )


def test_atom_candidate_hash_changes_only_with_patch_content():
    first = _patch()
    same = _patch()
    changed = KnowledgePatch(
        category=first.category,
        operation=first.operation,
        name=first.name,
        data={"description": "已经揭开", "confidence": 0.8},
    )

    assert build_atom_candidate_hash(first) == build_atom_candidate_hash(same)
    assert build_atom_candidate_hash(first) != build_atom_candidate_hash(changed)


@pytest.mark.asyncio
async def test_record_patch_atoms_creates_generated_candidates_without_canonical_merge():
    db = _AtomSession()
    project_id = uuid.uuid4()
    evidence_id = uuid.uuid4()

    result = await record_patch_atoms(
        db,
        project_id=project_id,
        chapter_index=12,
        patch_set=KnowledgePatchSet(patches=[_patch()]),
        evidence_id=evidence_id,
    )

    assert result == [db.atom]
    assert len(db.statements) == 1
    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    assert "ON CONFLICT DO NOTHING" in str(compiled)
    assert compiled.params["status"] == "candidate"
    assert compiled.params["authority"] == "generated"
    assert compiled.params["evidence_id"] == evidence_id
    assert compiled.params["valid_from_chapter"] == 12


@pytest.mark.asyncio
async def test_record_patch_atoms_can_exist_without_evidence():
    db = _AtomSession()
    result = await record_patch_atoms(
        db,
        project_id=uuid.uuid4(),
        chapter_index=12,
        patch_set=KnowledgePatchSet(patches=[_patch()]),
        evidence_id=None,
    )

    assert result == [db.atom]
    compiled = db.statements[0].compile(dialect=postgresql.dialect())
    assert compiled.params["evidence_id"] is None


def test_atom_review_lifecycle_is_explicit():
    candidate = SimpleNamespace(status="candidate", authority="generated")
    assert accept_atom_candidates([candidate]) == [candidate]
    assert candidate.status == "accepted"
    assert reject_atom_candidate(SimpleNamespace(status="candidate", authority="generated")).status == "rejected"
    assert supersede_atom(SimpleNamespace(status="candidate", authority="generated")).status == "superseded"

    with pytest.raises(ValueError):
        accept_atom_candidates([SimpleNamespace(status="rejected", authority="generated")])
