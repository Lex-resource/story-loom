"""Deterministic L2 scene-block aggregation and vector projection."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.knowledge import VectorOutbox
from models.novel_memory import NovelSceneBlock
from services.novel_memory_types import AUTHORITY_GENERATED, SCENE_BLOCK_ACTIVE, STORYLINE_MAIN
from services.pipeline_types import VectorOutboxStatus
from services.vector_constants import VECTOR_SCENE_BLOCK_ITEM_ID_TEMPLATE, VECTOR_SOURCE_SCENE_BLOCK


def build_scene_block_content_hash(
    *,
    summary: str,
    current_state: dict[str, Any],
    open_questions: list[Any],
    recent_changes: list[Any],
) -> str:
    payload = {
        "summary": summary or "",
        "current_state": current_state or {},
        "open_questions": open_questions or [],
        "recent_changes": recent_changes or [],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scene_block_vector_id(project_id: uuid.UUID, scope_type: str, scope_key: str) -> str:
    return VECTOR_SCENE_BLOCK_ITEM_ID_TEMPLATE.format(
        project_id=project_id,
        scope_type=scope_type,
        scope_key=scope_key,
    )


async def upsert_scene_block(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    scope_type: str,
    scope_key: str,
    summary: str,
    current_state: dict[str, Any] | None = None,
    open_questions: list[Any] | None = None,
    recent_changes: list[Any] | None = None,
    source_ref: str,
    source_chapter: int | None,
    valid_from_chapter: int | None = None,
    valid_to_chapter: int | None = None,
    branch_id: uuid.UUID | None = None,
    storyline_id: str = STORYLINE_MAIN,
    confidence: float = 0.5,
) -> tuple[NovelSceneBlock, bool]:
    """Create one new block version, returning an existing content match on retry."""
    state = current_state or {}
    questions = open_questions or []
    changes = recent_changes or []
    content_hash = build_scene_block_content_hash(
        summary=summary,
        current_state=state,
        open_questions=questions,
        recent_changes=changes,
    )
    existing = await db.scalar(
        select(NovelSceneBlock).where(
            NovelSceneBlock.project_id == project_id,
            NovelSceneBlock.branch_id == branch_id,
            NovelSceneBlock.storyline_id == storyline_id,
            NovelSceneBlock.scope_type == scope_type,
            NovelSceneBlock.scope_key == scope_key,
            NovelSceneBlock.content_hash == content_hash,
        )
    )
    if existing is not None:
        return existing, False

    for _attempt in range(5):
        max_version = await db.scalar(
            select(func.max(NovelSceneBlock.version)).where(
                NovelSceneBlock.project_id == project_id,
                NovelSceneBlock.branch_id == branch_id,
                NovelSceneBlock.storyline_id == storyline_id,
                NovelSceneBlock.scope_type == scope_type,
                NovelSceneBlock.scope_key == scope_key,
            )
        )
        values = {
            "project_id": project_id,
            "branch_id": branch_id,
            "storyline_id": storyline_id,
            "source_ref": source_ref,
            "source_chapter": source_chapter,
            "confidence": max(0.0, min(1.0, float(confidence))),
            "version": int(max_version or 0) + 1,
            "valid_from_chapter": valid_from_chapter,
            "valid_to_chapter": valid_to_chapter,
            "authority": AUTHORITY_GENERATED,
            "scope_type": scope_type,
            "scope_key": scope_key,
            "content_hash": content_hash,
            "summary": summary or "",
            "current_state": state,
            "open_questions": questions,
            "recent_changes": changes,
            "status": SCENE_BLOCK_ACTIVE,
        }
        await db.execute(pg_insert(NovelSceneBlock).values(**values).on_conflict_do_nothing())
        block = await db.scalar(
            select(NovelSceneBlock).where(
                NovelSceneBlock.project_id == project_id,
                NovelSceneBlock.branch_id == branch_id,
                NovelSceneBlock.storyline_id == storyline_id,
                NovelSceneBlock.scope_type == scope_type,
                NovelSceneBlock.scope_key == scope_key,
                NovelSceneBlock.content_hash == content_hash,
            )
        )
        if block is not None:
            return block, True
    raise RuntimeError(f"Could not persist scene block: {scope_type}/{scope_key}")


async def enqueue_scene_block_vector(
    db: AsyncSession,
    block: NovelSceneBlock,
) -> VectorOutbox:
    """Project only the compressed summary, with scope metadata for recall."""
    metadata = {
        "memory_layer": "scene_block",
        "project_id": str(block.project_id),
        "storyline_id": block.storyline_id,
        "scope_type": block.scope_type,
        "scope_key": block.scope_key,
        "version": block.version,
    }
    # Chroma metadata rejects None. Optional scope/timeline dimensions are
    # omitted for mainline blocks and open-ended validity windows.
    if block.branch_id is not None:
        metadata["branch_id"] = str(block.branch_id)
    if block.valid_from_chapter is not None:
        metadata["valid_from_chapter"] = block.valid_from_chapter
    if block.valid_to_chapter is not None:
        metadata["valid_to_chapter"] = block.valid_to_chapter
    item = {
        "id": scene_block_vector_id(block.project_id, block.scope_type, block.scope_key),
        "description": block.summary,
        "source": VECTOR_SOURCE_SCENE_BLOCK,
        "type": block.scope_type,
        "name": block.scope_key,
        "metadata": metadata,
    }
    outbox = VectorOutbox(
        project_id=block.project_id,
        chapter_index=block.source_chapter,
        payload={"items": [item]},
        status=VectorOutboxStatus.PENDING,
    )
    db.add(outbox)
    await db.flush()
    return outbox


async def aggregate_scene_block(
    db: AsyncSession,
    **kwargs: Any,
) -> NovelSceneBlock:
    block, created = await upsert_scene_block(db, **kwargs)
    if created:
        await enqueue_scene_block_vector(db, block)
    return block
