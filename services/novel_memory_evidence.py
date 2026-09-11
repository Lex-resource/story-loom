"""Idempotent, append-only capture for L0 novel memory evidence."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel_memory import NovelMemoryEvidence
from services.novel_memory_types import AUTHORITY_GENERATED, STORYLINE_MAIN


def build_evidence_content_hash(raw_content: str, extracted_data: Any) -> str:
    """Return a stable digest for the exact source and extractor output."""
    canonical = json.dumps(
        {"raw_content": raw_content or "", "extracted_data": extracted_data},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def chapter_evidence_source_ref(chapter_index: int, stage: str = "extractor") -> str:
    return f"chapter:{chapter_index}:{stage}"


async def capture_evidence(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    raw_content: str,
    extracted_data: Any,
    source_ref: str,
    source_chapter: int | None,
    stage: str,
    branch_id: uuid.UUID | None = None,
    storyline_id: str = STORYLINE_MAIN,
    confidence: float = 0.0,
    authority: str = AUTHORITY_GENERATED,
    valid_from_chapter: int | None = None,
    valid_to_chapter: int | None = None,
) -> NovelMemoryEvidence:
    """Insert evidence once and return the existing row on retries.

    This function intentionally never updates an existing row. It only uses
    the database conflict target to make concurrent worker retries converge.
    The caller owns the surrounding transaction and decides when to commit.
    """
    content_hash = build_evidence_content_hash(raw_content, extracted_data)
    values = {
        "project_id": project_id,
        "branch_id": branch_id,
        "storyline_id": storyline_id,
        "source_ref": source_ref,
        "source_chapter": source_chapter,
        "stage": stage,
        "content_hash": content_hash,
        "raw_content": raw_content or "",
        "extracted_data": extracted_data,
        "confidence": confidence,
        "authority": authority,
        "valid_from_chapter": valid_from_chapter,
        "valid_to_chapter": valid_to_chapter,
        "is_immutable": True,
    }
    insert_stmt = pg_insert(NovelMemoryEvidence).values(**values)
    await db.execute(insert_stmt.on_conflict_do_nothing())
    result = await db.execute(
        select(NovelMemoryEvidence).where(
            NovelMemoryEvidence.project_id == project_id,
            NovelMemoryEvidence.branch_id == branch_id,
            NovelMemoryEvidence.storyline_id == storyline_id,
            NovelMemoryEvidence.source_ref == source_ref,
            NovelMemoryEvidence.content_hash == content_hash,
        )
    )
    evidence = result.scalar_one_or_none()
    if evidence is None:
        raise RuntimeError(
            "Novel memory evidence insert did not return a persisted row"
        )
    return evidence


async def capture_chapter_extractor_evidence(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    chapter_index: int,
    chapter_content: str,
    extractor_output: dict[str, Any],
    branch_id: uuid.UUID | None = None,
    storyline_id: str = STORYLINE_MAIN,
) -> NovelMemoryEvidence:
    """Capture a chapter extractor result without touching canonical facts."""
    return await capture_evidence(
        db,
        project_id=project_id,
        raw_content=chapter_content,
        extracted_data=extractor_output,
        source_ref=chapter_evidence_source_ref(chapter_index),
        source_chapter=chapter_index,
        stage="extractor",
        branch_id=branch_id,
        storyline_id=storyline_id,
    )


async def capture_branch_generation_evidence(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    branch_id: uuid.UUID,
    storyline_id: str,
    chapter_index: int,
    chapter_content: str,
    generation_data: dict[str, Any],
) -> NovelMemoryEvidence:
    """Capture branch output in its own retrieval namespace."""
    return await capture_evidence(
        db,
        project_id=project_id,
        branch_id=branch_id,
        storyline_id=storyline_id,
        raw_content=chapter_content,
        extracted_data=generation_data,
        source_ref=f"character_branch:{branch_id}:chapter:{chapter_index}:generation",
        source_chapter=chapter_index,
        stage="branch_generation",
    )


async def list_evidence(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    branch_id: uuid.UUID | None = None,
    storyline_id: str = STORYLINE_MAIN,
    source_chapter: int | None = None,
    limit: int = 100,
) -> list[NovelMemoryEvidence]:
    """Read only one project/storyline namespace at a time.

    In particular, a mainline query uses ``branch_id IS NULL`` and cannot
    accidentally include character-branch evidence.
    """
    statement = select(NovelMemoryEvidence).where(
        NovelMemoryEvidence.project_id == project_id,
        NovelMemoryEvidence.branch_id == branch_id,
        NovelMemoryEvidence.storyline_id == storyline_id,
    )
    if source_chapter is not None:
        statement = statement.where(NovelMemoryEvidence.source_chapter == source_chapter)
    result = await db.execute(
        statement.order_by(NovelMemoryEvidence.source_chapter, NovelMemoryEvidence.created_at)
        .limit(max(1, min(limit, 500)))
    )
    return list(result.scalars().all())
