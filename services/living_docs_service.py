from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.novel import LivingDocVersion, Novel
from services import living_docs
from services.document_constants import ALL_DOC_TYPES, KNOWLEDGE_DOC_TYPES, OUTLINE_DOC_TYPES
from services.novel_constants import CHAPTER_VERSION_DIR_TEMPLATE
from services.pipeline_config_service import NovelFormatPolicy


async def get_living_docs(project_id: str, db: AsyncSession) -> dict:
    await _ensure_short_story_living_docs(project_id, db)
    return await living_docs.read_all_docs(project_id, db)


async def get_living_doc_versions(project_id: str, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(LivingDocVersion)
        .where(LivingDocVersion.project_id == uuid.UUID(project_id))
        .order_by(LivingDocVersion.chapter_index.desc())
    )
    versions = result.scalars().all()
    return [
        {"chapter_index": v.chapter_index, "doc_type": v.doc_type, "path": v.path, "checksum": v.checksum}
        for v in versions
    ]


async def get_living_doc_version_content(project_id: str, chapter_index: int, doc_type: str) -> dict:
    src = _version_dir(project_id, chapter_index) / f"{doc_type}.md"
    if not src.exists():
        raise HTTPException(status_code=404, detail="Versioned document not found")
    return {"content": src.read_text(encoding="utf-8")}


async def get_living_doc(project_id: str, doc_type: str, db: AsyncSession) -> dict:
    await _ensure_short_story_living_docs(project_id, db, doc_type=doc_type)
    content = await living_docs.read_doc(project_id, doc_type, db)
    if content is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"doc_type": doc_type, "content": content}


async def _ensure_short_story_living_docs(
    project_id: str,
    db: AsyncSession,
    *,
    doc_type: str | None = None,
) -> None:
    """Backfill short-story baseline docs when the UI reads them.

    The normal generation path writes these after outline creation. This
    idempotent guard prevents an empty Living Docs screen if a worker was
    running older code or a project was created before the sync hook existed.
    """
    if doc_type is not None and doc_type not in KNOWLEDGE_DOC_TYPES and doc_type not in OUTLINE_DOC_TYPES:
        return

    result = await db.execute(select(Novel).where(Novel.id == uuid.UUID(project_id)))
    novel = result.scalar_one_or_none()
    if not novel or not NovelFormatPolicy.from_format(novel.novel_format).use_short_skeleton_bootstrap:
        return
    if not isinstance(novel.outline, dict) or not novel.outline:
        return

    if doc_type and await living_docs.read_doc(project_id, doc_type, db):
        return
    if doc_type is None:
        missing_doc = False
        for required_doc_type in (*KNOWLEDGE_DOC_TYPES, *OUTLINE_DOC_TYPES):
            if not await living_docs.read_doc(project_id, required_doc_type, db):
                missing_doc = True
                break
        if not missing_doc:
            return

    from services.short_story_living_docs import sync_short_story_living_docs

    await sync_short_story_living_docs(db, novel)
    await db.commit()


async def update_living_doc(project_id: str, doc_type: str, content: str, db: AsyncSession) -> dict:
    import json
    from services.knowledge_markdown import knowledge_from_markdown
    from services.knowledge_types import CharacterKnowledge, ForeshadowingKnowledge, KnowledgeBase, PlotThreadKnowledge, WorldRuleKnowledge

    if doc_type in OUTLINE_DOC_TYPES:
        await living_docs.write_doc(project_id, doc_type, content, db)
        await db.commit()
        return {"doc_type": doc_type, "checksum": living_docs._checksum(content)}

    try:
        data_list = json.loads(content)
        items = []
        for data in data_list:
            if doc_type == "character_state": items.append(CharacterKnowledge(**data))
            elif doc_type == "world_state": items.append(WorldRuleKnowledge(**data))
            elif doc_type == "foreshadowing": items.append(ForeshadowingKnowledge(**data))
            elif doc_type == "plot_threads": items.append(PlotThreadKnowledge(**data))
            else: items.append(KnowledgeBase(**data))
    except Exception:
        items = knowledge_from_markdown(doc_type, content)

    checksum = await living_docs.write_knowledge(project_id, doc_type, items, db)
    if doc_type == "character_state":
        living_docs.delete_graph(project_id)
    return {"doc_type": doc_type, "checksum": checksum}


async def rollback_living_doc(project_id: str, chapter_index: int, db: AsyncSession) -> dict:
    versions_dir = _version_dir(project_id, chapter_index)
    if not versions_dir.exists():
        raise HTTPException(status_code=404, detail=f"Version for chapter {chapter_index} not found")

    from services.knowledge_markdown import knowledge_from_markdown
    # Use auto_commit=False so all 4 doc types are restored atomically.
    # If any one fails, none will be persisted.
    for doc_type in KNOWLEDGE_DOC_TYPES:
        src = versions_dir / f"{doc_type}.md"
        if src.exists():
            items = knowledge_from_markdown(doc_type, src.read_text(encoding="utf-8"))
            await living_docs.write_knowledge(project_id, doc_type, items, db, auto_commit=False)
    await db.commit()

    return {"status": "rolled_back", "chapter_index": chapter_index}


async def rebuild_living_docs(project_id: str, db: AsyncSession) -> dict:
    import json
    from services.knowledge_markdown import knowledge_from_markdown
    from services.knowledge_types import CharacterKnowledge, ForeshadowingKnowledge, KnowledgeBase, PlotThreadKnowledge, WorldRuleKnowledge

    doc_types = ALL_DOC_TYPES
    rebuilt = []
    for doc_type in doc_types:
        content = await living_docs.read_doc(project_id, doc_type, db)
        if content:
            try:
                data_list = json.loads(content)
                items = []
                for data in data_list:
                    if doc_type == "character_state": items.append(CharacterKnowledge(**data))
                    elif doc_type == "world_state": items.append(WorldRuleKnowledge(**data))
                    elif doc_type == "foreshadowing": items.append(ForeshadowingKnowledge(**data))
                    elif doc_type == "plot_threads": items.append(PlotThreadKnowledge(**data))
                    else: items.append(KnowledgeBase(**data))
                await living_docs.write_knowledge(project_id, doc_type, items, db)
            except Exception:
                items = knowledge_from_markdown(doc_type, content)
                await living_docs.write_knowledge(project_id, doc_type, items, db)
            rebuilt.append(doc_type)
    return {"status": "ok", "rebuilt": rebuilt}


def _version_dir(project_id: str, chapter_index: int) -> Path:
    return Path(settings.LIVING_DOCS_DIR) / project_id / "versions" / CHAPTER_VERSION_DIR_TEMPLATE.format(chapter_index)
