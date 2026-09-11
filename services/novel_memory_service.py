"""HTTP-independent queries and mutations for novel-memory views."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel_memory import (
    NovelMemoryAtom,
    NovelMemoryEvidence,
    NovelSceneBlock,
    ProjectDoctrine,
)
from services.novel_memory_atoms import transition_atom_status

DEFAULT_MEMORY_PAGE_SIZE = 200
MAX_MEMORY_PAGE_SIZE = 500


def _apply_page(statement, limit: int, offset: int):
    bounded_limit = min(max(int(limit), 1), MAX_MEMORY_PAGE_SIZE)
    bounded_offset = max(int(offset), 0)
    return statement.limit(bounded_limit).offset(bounded_offset)


def _serialize(value) -> dict:
    return {
        "id": str(value.id),
        "project_id": str(value.project_id),
        "branch_id": str(value.branch_id) if value.branch_id else None,
        "storyline_id": value.storyline_id,
        "source_ref": value.source_ref,
        "source_chapter": value.source_chapter,
        "confidence": value.confidence,
        "version": value.version,
        "valid_from_chapter": value.valid_from_chapter,
        "valid_to_chapter": value.valid_to_chapter,
        "authority": value.authority,
    }


async def memory_summary(db: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    count_for = lambda model: select(func.count()).select_from(model).where(model.project_id == project_id).scalar_subquery()
    result = await db.execute(
        select(
            count_for(NovelMemoryEvidence).label("evidence"),
            count_for(NovelMemoryAtom).label("atoms"),
            count_for(NovelSceneBlock).label("scene_blocks"),
            count_for(ProjectDoctrine).label("doctrines"),
        )
    )
    row = result.one()
    return {
        "evidence": row.evidence,
        "atoms": row.atoms,
        "scene_blocks": row.scene_blocks,
        "doctrines": row.doctrines,
    }


async def list_memory_atoms(
    db: AsyncSession,
    project_id: uuid.UUID,
    status: str | None = None,
    *,
    limit: int = DEFAULT_MEMORY_PAGE_SIZE,
    offset: int = 0,
) -> dict[str, list[dict]]:
    statement = (
        select(NovelMemoryAtom)
        .where(NovelMemoryAtom.project_id == project_id)
        .order_by(
            NovelMemoryAtom.source_chapter.desc(),
            NovelMemoryAtom.version.desc(),
            NovelMemoryAtom.id.asc(),
        )
    )
    if status:
        statement = statement.where(NovelMemoryAtom.status == status)
    statement = _apply_page(statement, limit, offset)
    atoms = list((await db.scalars(statement)).all())
    return {
        "items": [
            {
                **_serialize(atom),
                "memory_key": atom.memory_key,
                "atom_type": atom.atom_type,
                "statement": atom.statement,
                "data": atom.data,
                "status": atom.status,
                "evidence_id": str(atom.evidence_id) if atom.evidence_id else None,
            }
            for atom in atoms
        ]
    }


async def set_memory_atom_status(
    db: AsyncSession,
    project_id: uuid.UUID,
    atom_id: uuid.UUID,
    status: str,
) -> dict:
    atom = await db.scalar(
        select(NovelMemoryAtom).where(
            NovelMemoryAtom.id == atom_id,
            NovelMemoryAtom.project_id == project_id,
        )
    )
    if atom is None:
        raise LookupError("Memory atom not found")
    transition_atom_status(atom, status)
    await db.commit()
    return {"id": str(atom.id), "status": atom.status}


async def list_memory_scenes(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    limit: int = DEFAULT_MEMORY_PAGE_SIZE,
    offset: int = 0,
) -> dict[str, list[dict]]:
    statement = _apply_page(
        select(NovelSceneBlock)
        .where(NovelSceneBlock.project_id == project_id)
        .order_by(
            NovelSceneBlock.source_chapter.desc(),
            NovelSceneBlock.version.desc(),
            NovelSceneBlock.id.asc(),
        ),
        limit,
        offset,
    )
    scenes = list(
        (
            await db.scalars(
                statement
            )
        ).all()
    )
    return {
        "items": [
            {
                **_serialize(scene),
                "scope_type": scene.scope_type,
                "scope_key": scene.scope_key,
                "summary": scene.summary,
                "current_state": scene.current_state,
                "open_questions": scene.open_questions,
                "recent_changes": scene.recent_changes,
                "status": scene.status,
            }
            for scene in scenes
        ]
    }


async def list_memory_doctrines(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    limit: int = DEFAULT_MEMORY_PAGE_SIZE,
    offset: int = 0,
) -> dict[str, list[dict]]:
    statement = _apply_page(
        select(ProjectDoctrine)
        .where(
            ProjectDoctrine.project_id == project_id,
            ProjectDoctrine.is_active.is_(True),
        )
        .order_by(ProjectDoctrine.version.desc(), ProjectDoctrine.id.asc()),
        limit,
        offset,
    )
    doctrines = list(
        (
            await db.scalars(
                statement
            )
        ).all()
    )
    return {
        "items": [
            {
                **_serialize(doctrine),
                "doctrine_key": doctrine.doctrine_key,
                "doctrine_type": doctrine.doctrine_type,
                "content": doctrine.content,
                "data": doctrine.data,
                "is_active": doctrine.is_active,
            }
            for doctrine in doctrines
        ]
    }


async def list_memory_evidence(
    db: AsyncSession,
    project_id: uuid.UUID,
    *,
    limit: int = DEFAULT_MEMORY_PAGE_SIZE,
    offset: int = 0,
) -> dict[str, list[dict]]:
    statement = _apply_page(
        select(NovelMemoryEvidence)
        .where(NovelMemoryEvidence.project_id == project_id)
        .order_by(
            NovelMemoryEvidence.source_chapter.desc(),
            NovelMemoryEvidence.created_at.desc(),
            NovelMemoryEvidence.id.asc(),
        ),
        limit,
        offset,
    )
    evidence = list(
        (
            await db.scalars(
                statement
            )
        ).all()
    )
    return {
        "items": [
            {
                **_serialize(item),
                "stage": item.stage,
                "content_hash": item.content_hash,
                "extracted_data": item.extracted_data,
                "is_immutable": item.is_immutable,
            }
            for item in evidence
        ]
    }
