from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from services import living_docs
from services.knowledge_patch_handlers import apply_patch
from services.knowledge_patch_models import KnowledgePatch, KnowledgePatchSet, KnowledgePatchSummary, PatchCategory
from services.knowledge_types import CATEGORY_TO_DOC_TYPE


async def apply_knowledge_patches(
    project_id: str,
    patch_set: KnowledgePatchSet,
    db: AsyncSession,
    chapter_index: int = 1,
) -> KnowledgePatchSummary:
    by_category: dict[PatchCategory, list[KnowledgePatch]] = {}
    for patch in patch_set.patches:
        by_category.setdefault(patch.category, []).append(patch)

    changed_categorys: list[PatchCategory] = []
    changed_items: list[str] = []
    for category, patches in by_category.items():
        doc_type = CATEGORY_TO_DOC_TYPE.get(category, category)
        items = await living_docs.read_knowledge(project_id, doc_type, db)
        indexed = {item.name: item for item in items}
        for patch in patches:
            apply_patch(indexed, patch, chapter_index=chapter_index)
            changed_items.append(f"{patch.category}:{patch.name}")
        await living_docs.write_knowledge(
            project_id,
            doc_type,
            list(indexed.values()),
            db,
            check_readonly=False,
        )
        changed_categorys.append(category)

    return KnowledgePatchSummary(
        changed_categorys=changed_categorys,
        changed_items=changed_items,
        vector_items=patch_set.vector_items,
    )
