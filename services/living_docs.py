import uuid
import json
from typing import Optional, Dict
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models.novel import SettingsDoc
from services.document_constants import (
    ALL_DOC_TYPES,
    OUTLINE_DOC_TYPES,
)
from services.knowledge_types import (
    KnowledgeDocType,
    KnowledgeModel,
    DOC_TYPE_TO_CATEGORY,
)
from services.living_docs_formatting import (
    compile_foreshadowing,
    format_act_outline_to_markdown,
    format_outline_to_markdown,
)
from services.living_docs_files import (
    archive_doc,
    checksum,
    delete_graph,
    file_path,
    read_current_doc,
    read_graph,
    snapshot_current_doc,
    write_current_doc,
    write_graph,
)
from services.living_docs_repository import (
    read_all_knowledge as repository_read_all_knowledge,
    read_knowledge as repository_read_knowledge,
    write_knowledge as repository_write_knowledge,
)

DEFAULT_NAMES = {
    "world_state": "境界与地理设定",
    "foreshadowing": "主线伏笔设定",
    "plot_threads": "剧情线索设定",
    "global_outline": "全书整体大纲",
    "act_outline": "分幕情节大纲",
}


_checksum = checksum
_file_path = file_path


async def read_knowledge(project_id: str, doc_type: KnowledgeDocType, db: Optional[AsyncSession] = None) -> list[KnowledgeModel]:
    return await repository_read_knowledge(project_id, doc_type, db)


async def read_all_knowledge(
    project_id: str, db: Optional[AsyncSession] = None
) -> Dict[str, list[KnowledgeModel]]:
    return await repository_read_all_knowledge(project_id, db)


async def write_knowledge(
    project_id: str,
    doc_type: KnowledgeDocType,
    items: list[KnowledgeModel],
    db: Optional[AsyncSession] = None,
    check_readonly: bool = True,
    auto_commit: bool = True,
) -> str:
    return await repository_write_knowledge(
        project_id,
        doc_type,
        items,
        db,
        check_readonly=check_readonly,
        auto_commit=auto_commit,
    )


async def write_doc(project_id: str, doc_type: str, content: str, db: Optional[AsyncSession] = None) -> None:
    """Write raw document content to filesystem.

    Used for self-healing: when DB has no record but filesystem does (or when
    auto-seeding global_outline/act_outline from novel.outline), persist the
    content to disk so subsequent reads can find it. DB sync for structured
    knowledge items is handled separately by write_knowledge.
    """
    write_current_doc(project_id, doc_type, content)

    # Outline docs are raw Markdown files. If a previous code path accidentally
    # wrote them into settings_docs, deactivate those structured rows so
    # read_doc will fall back to the Markdown file again.
    if doc_type in OUTLINE_DOC_TYPES:
        pid = uuid.UUID(project_id)
        category = DOC_TYPE_TO_CATEGORY.get(doc_type)
        if category:
            async def _deactivate(session: AsyncSession) -> None:
                await session.execute(
                    update(SettingsDoc)
                    .where(SettingsDoc.project_id == pid, SettingsDoc.category == category)
                    .values(is_active=False)
                )

            if db:
                await _deactivate(db)
            else:
                async with async_session() as session:
                    await _deactivate(session)
                    await session.commit()


async def read_doc(project_id: str, doc_type: str, db: Optional[AsyncSession] = None) -> Optional[str]:
    category = DOC_TYPE_TO_CATEGORY.get(doc_type)
    if not category:
        return None

    # Outline docs are authored and displayed as raw Markdown. Prefer the
    # filesystem source so legacy structured rows cannot mask the real outline.
    if doc_type in OUTLINE_DOC_TYPES:
        content = read_current_doc(project_id, doc_type)
        if content is not None:
            return content

    async def _query(session: AsyncSession):
        res = await session.execute(
            select(SettingsDoc)
            .where(
                SettingsDoc.project_id == uuid.UUID(project_id),
                SettingsDoc.category == category,
                SettingsDoc.is_active == True
            )
            .order_by(SettingsDoc.name)
        )
        return res.scalars().all()

    docs = []
    if db:
        docs = await _query(db)
    else:
        async with async_session() as session:
            docs = await _query(session)

    if docs:
        if doc_type in ALL_DOC_TYPES:
            data_list = []
            for doc in docs:
                if isinstance(doc.data, dict):
                    data_list.append(doc.data)
                elif isinstance(doc.data, str):
                    try:
                        data_list.append(json.loads(doc.data))
                    except Exception as je:
                        print(f"[LivingDocs WARN] Failed to parse doc data JSON: {je}")
            res_content = json.dumps(data_list, ensure_ascii=False, indent=2)

        # Self-healing: restore missing files on disk.
        # _file_path returns a .md path (same convention used by write_doc),
        # so the restored file must also be written as .md, otherwise the
        # filesystem fallback read (which looks for the .md path) would never
        # find the self-healed file.
        try:
            p = file_path(project_id, doc_type)
            if not p.exists():
                write_current_doc(project_id, doc_type, res_content)
        except Exception as she:
            print(f"[LivingDocs WARN] Self-heal failed for {project_id}/{doc_type}: {she}")

        return res_content

    # Fallback to filesystem
    content = read_current_doc(project_id, doc_type)
    if content is not None:
        # Try to seed to DB on the fly
        try:
            await write_doc(project_id, doc_type, content, db)
        except Exception as e:
            print(f"[Warning] Failed to sync document {doc_type} to database: {e}")
        return content

    # Auto-seed global_outline and act_outline from novel.outline if not exists
    if doc_type in OUTLINE_DOC_TYPES:
        from models.novel import Novel
        async def _query_novel(session: AsyncSession):
            res = await session.execute(
                select(Novel).where(Novel.id == uuid.UUID(project_id))
            )
            return res.scalar_one_or_none()

        novel = None
        if db:
            novel = await _query_novel(db)
        else:
            async with async_session() as session:
                novel = await _query_novel(session)

        if novel and novel.outline:
            if doc_type == "global_outline":
                content = format_outline_to_markdown(novel.outline)
            else:
                content = format_act_outline_to_markdown(novel.outline)

            if content:
                try:
                    await write_doc(project_id, doc_type, content, db)
                except Exception as e:
                    print(f"[Warning] Failed to auto-seed {doc_type} from outline: {e}")
                return content
    return None


async def snapshot_doc(project_id: str, chapter_index: int, doc_type: str, db: Optional[AsyncSession] = None) -> str:
    content = await read_doc(project_id, doc_type, db)
    if not content:
        # Fallback to filesystem
        content = read_current_doc(project_id, doc_type)
        if not content:
            return ""

    return snapshot_current_doc(project_id, chapter_index, doc_type, content)


async def read_all_docs(project_id: str, db: Optional[AsyncSession] = None) -> dict:
    docs = {}
    for doc_type in ALL_DOC_TYPES:
        content = await read_doc(project_id, doc_type, db)
        if content:
            docs[doc_type] = content
    return docs
