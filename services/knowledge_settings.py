from __future__ import annotations

import json
from typing import Any

from services.knowledge_constants import (
    FORESHADOWING_DEFAULT_IMPORTANCE,
    FORESHADOWING_STATUS_ACTIVE,
    KNOWLEDGE_TIMESTAMP_FORMAT,
    PATCH_CATEGORY_CHARACTER,
    PATCH_CATEGORY_FORESHADOWING,
    PATCH_CATEGORY_PLOT_THREAD,
    PATCH_CATEGORY_WORLD_RULE,
)
from services.knowledge_types import (
    CharacterKnowledge,
    ForeshadowingKnowledge,
    KnowledgeBase,
    KnowledgeModel,
    PlotThreadKnowledge,
    WorldRuleKnowledge,
)
from services.knowledge_patch_handlers import relationships_for_attributes

_FORESHADOWING_RESERVED_ATTR_KEYS = {
    "name",
    "category",
    "body",
    "attributes",
    "aliases",
    "status",
    "importance",
    "chapter",
    "chapter_created",
    "chapter_updated",
    "created_at",
    "updated_at",
    "description",
    "resolved_chapter",
    "cancelled_chapter",
}


def knowledge_from_settings_doc(doc) -> KnowledgeModel:
    category = getattr(doc, "category", "")
    data = getattr(doc, "data", None) or {}
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {"content": data}
    name = getattr(doc, "name", data.get("name", ""))
    content = getattr(doc, "content", "") or ""
    created_str = _timestamp(getattr(doc, "created_at", None))
    updated_str = _timestamp(getattr(doc, "updated_at", None))

    if category == PATCH_CATEGORY_CHARACTER:
        return CharacterKnowledge(
            name=name,
            body=data.get("body", content),
            attributes=data.get("attributes", data),
            created_at=created_str,
            updated_at=updated_str,
        )
    if category == PATCH_CATEGORY_WORLD_RULE:
        return WorldRuleKnowledge(
            name=name,
            body=data.get("body", content),
            attributes=data.get("attributes", data),
            rule_type=data.get("rule_type", "") or data.get("type", ""),
            created_at=created_str,
            updated_at=updated_str,
        )
    if category == PATCH_CATEGORY_FORESHADOWING:
        return _foreshadowing_from_settings_doc(name, content, data, created_str, updated_str)
    if category == PATCH_CATEGORY_PLOT_THREAD:
        return PlotThreadKnowledge(
            name=name,
            progress=data.get("progress", ""),
            body="",
            chapter_created=data.get("chapter_created"),
            chapter_updated=data.get("chapter_updated"),
            created_at=created_str,
            updated_at=updated_str,
        )
    return KnowledgeBase(name=name, category=category or "generic", body=content, attributes=data)


def settings_doc_payload_from_knowledge(item: KnowledgeModel) -> tuple[str, str, dict[str, Any]]:
    data = item.model_dump()
    content = format_markdown_from_knowledge(item)
    if isinstance(item, ForeshadowingKnowledge):
        return PATCH_CATEGORY_FORESHADOWING, content, data
    if isinstance(item, CharacterKnowledge):
        return PATCH_CATEGORY_CHARACTER, content, data
    if isinstance(item, WorldRuleKnowledge):
        return PATCH_CATEGORY_WORLD_RULE, content, data
    if isinstance(item, PlotThreadKnowledge):
        return PATCH_CATEGORY_PLOT_THREAD, content, data
    return item.category, content, data


def format_markdown_from_knowledge(item: KnowledgeModel) -> str:
    lines = [f"# {item.name}"]
    if getattr(item, "status", None) and item.status != FORESHADOWING_STATUS_ACTIVE:
        lines.append(f"**状态**: {item.status}")
    if getattr(item, "importance", None) and item.importance != FORESHADOWING_DEFAULT_IMPORTANCE:
        lines.append(f"**重要度**: {item.importance}")

    if item.body:
        lines.append(f"\n{item.body}")

    if getattr(item, "attributes", None):
        lines.append("\n## 属性设定")
        for k, v in item.attributes.items():
            if isinstance(item, CharacterKnowledge) and k == "relationships":
                continue
            if isinstance(v, list):
                lines.append(f"### {k}")
                for sub in v:
                    if isinstance(sub, dict):
                        sub_str = ", ".join([f"{sk}: {sv}" for sk, sv in sub.items()])
                        lines.append(f"- {sub_str}")
                    else:
                        lines.append(f"- {sub}")
            elif isinstance(v, dict):
                lines.append(f"### {k}")
                for sk, sv in v.items():
                    lines.append(f"- **{sk}**: {sv}")
            else:
                lines.append(f"- **{k}**: {v}")

    if isinstance(item, CharacterKnowledge):
        relationships = relationships_for_attributes(item.attributes)
        if relationships:
            lines.append("\n## 关系")
            for relationship in relationships:
                description = relationship.get("description", "")
                suffix = f"：{description}" if description else ""
                lines.append(f"- {relationship['to']}（{relationship.get('label', '相关')}）{suffix}")

    if isinstance(item, ForeshadowingKnowledge):
        lines.append(f"\n- 埋设章节: {item.chapter}")
        if item.resolved_chapter:
            lines.append(f"- 回收章节: {item.resolved_chapter}")
        if item.cancelled_chapter:
            lines.append(f"- 作废章节: {item.cancelled_chapter}")

    if isinstance(item, PlotThreadKnowledge):
        if item.progress:
            lines.append(f"\n## 当前进度\n{item.progress}")
        if getattr(item, "next_step", ""):
            lines.append(f"\n## 下一步计划\n{item.next_step}")

    return "\n".join(lines)


def as_foreshadowing(item: KnowledgeModel) -> ForeshadowingKnowledge:
    if isinstance(item, ForeshadowingKnowledge):
        return item
    return ForeshadowingKnowledge(name=item.name, description=item.body, attributes=item.attributes)


def _foreshadowing_from_settings_doc(
    name: str,
    content: str,
    data: dict[str, Any],
    created_str: str | None,
    updated_str: str | None,
) -> ForeshadowingKnowledge:
    if not data:
        try:
            data = json.loads(content)
        except Exception:
            data = {"description": content}
    attrs = data.get("attributes", {})
    if not isinstance(attrs, dict):
        attrs = {}
    attrs = {k: v for k, v in attrs.items() if k not in _FORESHADOWING_RESERVED_ATTR_KEYS}
    return ForeshadowingKnowledge(
        name=name,
        description=data.get("description", content),
        status=data.get("status", FORESHADOWING_STATUS_ACTIVE),
        importance=data.get("importance", FORESHADOWING_DEFAULT_IMPORTANCE),
        chapter=int(data.get("chapter") or 1),
        resolved_chapter=data.get("resolved_chapter"),
        cancelled_chapter=data.get("cancelled_chapter"),
        attributes=attrs,
        created_at=created_str,
        updated_at=updated_str,
    )


def _timestamp(value) -> str | None:
    if hasattr(value, "strftime"):
        return value.strftime(KNOWLEDGE_TIMESTAMP_FORMAT)
    if value:
        return str(value)
    return None
