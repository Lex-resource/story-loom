"""Independent vector projection for character branch chapters."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.character_branches import CharacterBranch, CharacterBranchChapter
from models.novel import VectorOutbox
from services.character_constants import (
    CHARACTER_BRANCH_VECTOR_COLLECTION_PREFIX,
    CHARACTER_BRANCH_VECTOR_ITEM_ID_TEMPLATE,
    CHARACTER_BRANCH_VECTOR_SOURCE,
)
from services.pipeline_types import VectorOutboxStatus


def branch_vector_collection_name(branch_id) -> str:
    return f"{CHARACTER_BRANCH_VECTOR_COLLECTION_PREFIX}{branch_id}"


async def enqueue_branch_chapter_vector(
    db: AsyncSession,
    branch: CharacterBranch,
    chapter: CharacterBranchChapter,
) -> VectorOutbox:
    content = chapter.content or chapter.edited_content or chapter.draft_content or ""
    item_id = CHARACTER_BRANCH_VECTOR_ITEM_ID_TEMPLATE.format(
        branch_id=branch.id,
        chapter_index=chapter.chapter_index,
    )
    item = {
        "id": item_id,
        "description": content,
        "source": CHARACTER_BRANCH_VECTOR_SOURCE,
        "type": "branch_chapter",
        "name": chapter.title,
        "metadata": {
            "branch_id": str(branch.id),
            "storyline_id": branch.storyline_id,
            "branch_chapter_index": chapter.chapter_index,
            "anchor_main_chapter": branch.anchor_main_chapter,
        },
    }
    outbox = VectorOutbox(
        project_id=branch.project_id,
        chapter_index=chapter.chapter_index,
        payload={
            "collection_name": branch_vector_collection_name(branch.id),
            "items": [item],
        },
        status=VectorOutboxStatus.PENDING,
    )
    db.add(outbox)
    await db.flush()
    return outbox


async def clear_branch_vector_namespace(branch_id) -> None:
    from services.vector_chroma import delete_collection

    collection_name = branch_vector_collection_name(branch_id)
    await delete_collection(collection_name)


async def discard_pending_branch_vectors(db: AsyncSession, branch_id) -> int:
    """Remove unprojected vectors before a branch is archived."""
    collection_name = branch_vector_collection_name(branch_id)
    result = await db.execute(
        select(VectorOutbox).where(
            VectorOutbox.status.in_((VectorOutboxStatus.PENDING, VectorOutboxStatus.SYNCING)),
        )
    )
    removed = 0
    for outbox in result.scalars().all():
        if (outbox.payload or {}).get("collection_name") != collection_name:
            continue
        await db.delete(outbox)
        removed += 1
    return removed
