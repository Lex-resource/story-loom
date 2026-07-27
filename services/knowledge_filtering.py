"""章节内容过滤：从全量设定文档中筛选出与当前章节相关的子集。

提供三类过滤函数：
- get_filtered_world_state: 按文档名匹配 + 向量召回
- get_filtered_foreshadowing: 按 active 状态 + 描述关键词 + 向量召回
- get_filtered_character_state: 按人物名/别名/主角名匹配章节正文

本模块仅做读取过滤，不写入任何 living_doc。被知识合并服务与生成任务调用。
"""
from __future__ import annotations

import json
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import SettingsDoc


# ---------------------------------------------------------------------------
# World state filtering
# ---------------------------------------------------------------------------

async def get_filtered_world_state(db: AsyncSession, project_id: uuid.UUID, chapter_content: str) -> str:
    """筛选与当前章节相关的世界规则文档。

    匹配策略：
    1. 全局通用规则文档始终包含；
    2. 文档名出现在章节正文中的包含；
    3. 向量召回命中且文档内容含召回文本的包含。
    """
    res = await db.execute(
        select(SettingsDoc)
        .where(
            SettingsDoc.project_id == project_id,
            SettingsDoc.category == "world_rule",
            SettingsDoc.is_active == True
        )
    )
    docs = res.scalars().all()
    if not docs:
        return ""

    matched_docs = []
    general_doc = next((d for d in docs if d.name == "全局通用规则"), None)
    if general_doc:
        matched_docs.append(general_doc)

    for doc in docs:
        if doc.name == "全局通用规则":
            continue
        if doc.name in chapter_content:
            matched_docs.append(doc)

    try:
        from services.vector_store import query_collection
        vector_res = await query_collection(
            collection_name=f"project_{project_id}",
            query_texts=[chapter_content[:2000]],
            n_results=5,
            where={"$and": [{"source": "setting"}, {"type": "world_state"}]}
        )
        matched_texts = vector_res.get("documents", [[]])[0]
        for doc in docs:
            if doc in matched_docs:
                continue
            for text_val in matched_texts:
                if text_val in doc.content:
                    matched_docs.append(doc)
                    break
    except Exception as e:
        print(f"[chapter_filtering] world_state vector filter failed: {e}")

    formatted_docs = []
    for doc in matched_docs:
        content_val = doc.content.strip()
        if not content_val:
            continue
        lines_val = content_val.split('\n')
        first_line_val = lines_val[0].strip()
        if not first_line_val.startswith('#'):
            lines_val[0] = f"## {first_line_val}"
        formatted_docs.append('\n'.join(lines_val))
    return "\n\n".join(formatted_docs)


# ---------------------------------------------------------------------------
# Foreshadowing filtering
# ---------------------------------------------------------------------------

async def get_filtered_foreshadowing(db: AsyncSession, project_id: uuid.UUID, chapter_content: str) -> str:
    """筛选与当前章节相关的活跃伏笔文档。"""
    res = await db.execute(
        select(SettingsDoc)
        .where(
            SettingsDoc.project_id == project_id,
            SettingsDoc.category == "foreshadowing",
            SettingsDoc.is_active == True
        )
    )
    docs = res.scalars().all()
    if not docs:
        return ""

    matched_docs = []

    for doc in docs:
        try:
            data = json.loads(doc.content)
            desc = data.get("description", "")
            status = data.get("status", "active")
        except Exception:
            desc = doc.content
            status = "active"

        if status != "active":
            continue

        words = re.findall(r'[\u4e00-\u9fa5]{2,}', desc)
        if any(word in chapter_content for word in words):
            matched_docs.append(doc)

    try:
        from services.vector_store import query_collection
        vector_res = await query_collection(
            collection_name=f"project_{project_id}",
            query_texts=[chapter_content[:2000]],
            n_results=5,
            where={"$and": [{"source": "setting"}, {"type": "foreshadowing"}]}
        )
        matched_texts = vector_res.get("documents", [[]])[0]
        for doc in docs:
            if doc in matched_docs:
                continue
            try:
                data = json.loads(doc.content)
                desc = data.get("description", "")
                status = data.get("status", "active")
            except Exception:
                desc = doc.content
                status = "active"

            if status != "active":
                continue

            for text_val in matched_texts:
                if text_val in desc or desc in text_val:
                    matched_docs.append(doc)
                    break
    except Exception as e:
        print(f"[chapter_filtering] foreshadowing vector filter failed: {e}")

    from services.living_docs import compile_foreshadowing
    return compile_foreshadowing(matched_docs)


# ---------------------------------------------------------------------------
# Character state filtering
# ---------------------------------------------------------------------------

def get_filtered_character_state(
    character_state_txt: str, chapter_content: str, protagonist_name: str | None
) -> str:
    """从全量人物状态 markdown 中筛选出现在当前章节中的人物块。

    主角（protagonist_name）始终包含。匹配规则：
    1. 解析 markdown 中 ## name 块；
    2. 提取括号内别名 + 末 2 字作为简称；
    3. 任一别名/简称出现在 chapter_content 中则保留。
    """
    from services.vector_store import parse_character_state

    char_blocks = parse_character_state(character_state_txt)
    matched_chars = []
    for char_name_full, block in char_blocks:
        base_name = char_name_full
        aliases: list[str] = []
        if "（" in base_name or "(" in base_name:
            base_name = re.sub(r'[（\(].*?[）\)]', '', char_name_full).strip()
            alias_match = re.search(r'[（\(](.*?)[）\)]', char_name_full)
            if alias_match:
                aliases.extend([a.strip() for a in alias_match.group(1).split(",") if a.strip()])

        if len(base_name) >= 3:
            aliases.append(base_name[-2:])

        match_targets = [base_name] + aliases

        if any(target in chapter_content for target in match_targets) \
                or base_name == protagonist_name \
                or char_name_full == protagonist_name:
            matched_chars.append(block)
    return "\n\n".join(matched_chars)
