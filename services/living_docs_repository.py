"""SettingsDoc repository operations for structured living-doc knowledge."""
import json
import uuid
from typing import Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models.novel import SettingsDoc
from services.knowledge_settings import (
    knowledge_from_settings_doc,
    settings_doc_payload_from_knowledge,
)
from services.knowledge_types import (
    DOC_TYPE_TO_CATEGORY,
    KnowledgeDocType,
    KnowledgeModel,
)
from services.living_docs_files import checksum


async def read_knowledge(
    project_id: str, doc_type: KnowledgeDocType, db: Optional[AsyncSession] = None
) -> list[KnowledgeModel]:
    category = DOC_TYPE_TO_CATEGORY.get(doc_type)
    if not category:
        return []

    async def _query(session: AsyncSession) -> list[KnowledgeModel]:
        res = await session.execute(
            select(SettingsDoc)
            .where(
                SettingsDoc.project_id == uuid.UUID(project_id),
                SettingsDoc.category == category,
                SettingsDoc.is_active == True,
            )
            .order_by(SettingsDoc.name)
        )
        return [knowledge_from_settings_doc(doc) for doc in res.scalars().all()]

    if db:
        return await _query(db)
    async with async_session() as session:
        return await _query(session)


async def read_all_knowledge(
    project_id: str, db: Optional[AsyncSession] = None
) -> Dict[str, list[KnowledgeModel]]:
    """Batch-read knowledge for all mapped knowledge doc types in one query."""
    category_to_doc_type: Dict[str, str] = {
        category: doc_type for doc_type, category in DOC_TYPE_TO_CATEGORY.items()
    }

    async def _query(session: AsyncSession) -> Dict[str, list[KnowledgeModel]]:
        res = await session.execute(
            select(SettingsDoc)
            .where(
                SettingsDoc.project_id == uuid.UUID(project_id),
                SettingsDoc.is_active == True,
                SettingsDoc.category.in_(list(category_to_doc_type.keys())),
            )
            .order_by(SettingsDoc.category, SettingsDoc.name)
        )
        grouped: Dict[str, list[KnowledgeModel]] = {
            doc_type: [] for doc_type in category_to_doc_type.values()
        }
        for doc in res.scalars().all():
            doc_type = category_to_doc_type.get(doc.category)
            if doc_type is None:
                continue
            grouped[doc_type].append(knowledge_from_settings_doc(doc))
        return grouped

    if db:
        return await _query(db)
    async with async_session() as session:
        return await _query(session)


async def write_knowledge(
    project_id: str,
    doc_type: KnowledgeDocType,
    items: list[KnowledgeModel],
    db: Optional[AsyncSession] = None,
    check_readonly: bool = True,
    auto_commit: bool = True,
) -> str:
    pid = uuid.UUID(project_id)
    markdown = "\n".join(json.dumps(i.model_dump(), ensure_ascii=False) for i in items)

    async def _write(session: AsyncSession) -> None:
        if check_readonly:
            from models.novel import Novel
            from services.pipeline_config_service import get_pipeline_config

            res = await session.execute(select(Novel).where(Novel.id == pid))
            novel = res.scalar_one_or_none()
            if novel:
                config = await get_pipeline_config(session, novel.novel_format)
                if doc_type in config.readonly_docs:
                    raise ValueError(
                        f"文档类型 '{doc_type}' 在 {novel.novel_format} 模式下为只读，"
                        f"无法修改。请在项目设置中调整。"
                    )

        category = DOC_TYPE_TO_CATEGORY.get(doc_type)
        if not category:
            return
        await session.execute(
            update(SettingsDoc)
            .where(SettingsDoc.project_id == pid, SettingsDoc.category == category)
            .values(is_active=False)
        )
        for item in items:
            item_category, content, data = settings_doc_payload_from_knowledge(item)
            res = await session.execute(
                select(SettingsDoc)
                .where(
                    SettingsDoc.project_id == pid,
                    SettingsDoc.category == item_category,
                    SettingsDoc.name == item.name,
                )
            )
            existing = res.scalar_one_or_none()
            if existing:
                existing.content = content
                existing.data = data
                existing.is_active = True
            else:
                session.add(
                    SettingsDoc(
                        project_id=pid,
                        category=item_category,
                        name=item.name,
                        content=content,
                        data=data,
                        is_active=True,
                    )
                )
        if auto_commit:
            await session.commit()

    if db:
        await _write(db)
    else:
        async with async_session() as session:
            await _write(session)

    return checksum(markdown)
