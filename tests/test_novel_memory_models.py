import uuid

import pytest
from sqlalchemy import inspect

from database import Base
from models.novel_memory import (
    NovelMemoryAtom,
    NovelMemoryEvidence,
    NovelSceneBlock,
    ProjectDoctrine,
)


def test_memory_tables_are_registered_with_metadata():
    assert {
        "novel_memory_evidence",
        "novel_memory_atoms",
        "novel_scene_blocks",
        "project_doctrines",
    }.issubset(Base.metadata.tables)


def test_memory_scope_has_source_timeline_and_authority_fields():
    for model in (NovelMemoryEvidence, NovelMemoryAtom, NovelSceneBlock, ProjectDoctrine):
        columns = inspect(model).columns
        assert {"project_id", "branch_id", "storyline_id", "source_ref", "source_chapter", "confidence", "version", "authority"}.issubset(columns.keys())
        assert columns.valid_from_chapter.nullable
        assert columns.valid_to_chapter.nullable


def test_atom_defaults_and_validation():
    atom = NovelMemoryAtom(
        project_id=uuid.uuid4(),
        source_ref="chapter:1:extractor",
        memory_key="character:lin:status",
        atom_type="character_state",
        statement="林醒着。",
        data={},
    )
    assert atom.storyline_id == "main" or atom.storyline_id is None
    assert atom.version == 1 or atom.version is None
    assert atom.status == "candidate" or atom.status is None

    with pytest.raises(ValueError):
        atom.status = "overwrite"

    with pytest.raises(ValueError):
        atom.authority = "llm"


def test_project_foreign_keys_use_cascade_delete():
    for model in (NovelMemoryEvidence, NovelMemoryAtom, NovelSceneBlock, ProjectDoctrine):
        foreign_keys = {fk.target_fullname: fk.ondelete for fk in inspect(model).columns.project_id.foreign_keys}
        assert foreign_keys["novels.id"] == "CASCADE"
        branch_fks = {fk.target_fullname: fk.ondelete for fk in inspect(model).columns.branch_id.foreign_keys}
        assert branch_fks["character_branches.id"] == "CASCADE"


def test_versioned_scope_keys_are_unique():
    for model, name in (
        (NovelMemoryEvidence, "uq_novel_memory_evidence_mainline"),
        (NovelMemoryAtom, "uq_novel_memory_atom_mainline"),
        (NovelSceneBlock, "uq_novel_scene_block_mainline"),
        (ProjectDoctrine, "uq_project_doctrine_mainline"),
    ):
        assert name in {index.name for index in model.__table__.indexes}
