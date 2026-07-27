from __future__ import annotations

import json
import re

from services.knowledge_constants import (
    FORESHADOWING_DEFAULT_IMPORTANCE,
    FORESHADOWING_STATUS_ACTIVE,
    FORESHADOWING_STATUS_CANCELLED,
    FORESHADOWING_STATUS_RESOLVED,
)
from services.knowledge_types import (
    DOC_TYPE_TO_CATEGORY,
    CharacterKnowledge,
    ForeshadowingKnowledge,
    KnowledgeBase,
    KnowledgeDocType,
    KnowledgeModel,
    PlotThreadKnowledge,
)
from services.knowledge_patch_handlers import relationships_for_attributes


def knowledge_to_markdown(doc_type: str, items: list[KnowledgeModel]) -> str:
    """Render structured knowledge as markdown text."""
    if not items:
        return ""

    if doc_type == "character_state":
        lines: list[str] = []
        for item in items:
            lines.append(f"## {item.name}")
            for k, v in (item.attributes or {}).items():
                if k == "relationships":
                    continue
                lines.append(f"- {k}: {v}")
            relationships = relationships_for_attributes(item.attributes)
            if relationships:
                lines.append("")
                lines.append("### 关系")
                for relationship in relationships:
                    description = relationship.get("description", "")
                    suffix = f"：{description}" if description else ""
                    lines.append(f"- {relationship['to']}（{relationship.get('label', '相关')}）{suffix}")
            if item.body:
                lines.append("")
                lines.append(item.body)
            lines.append("")
        return "\n".join(lines).strip()

    if doc_type == "foreshadowing":
        lines: list[str] = []
        for item in items:
            fs = item if isinstance(item, ForeshadowingKnowledge) else ForeshadowingKnowledge(
                name=item.name, description=item.body, attributes=item.attributes
            )
            desc = fs.description or fs.body or ""
            lines.append(f"- [ID: {fs.name}] {desc}")
        return "\n".join(lines)

    if doc_type == "plot_threads":
        lines: list[str] = []
        for item in items:
            progress = getattr(item, "progress", "") or item.body
            lines.append(f"- {item.name}: {progress}")
        return "\n".join(lines)

    return "\n".join([json.dumps(i.model_dump(), ensure_ascii=False) for i in items])


def knowledge_from_markdown(doc_type: KnowledgeDocType, content: str) -> list[KnowledgeModel]:
    if not content:
        return []

    if doc_type == "plot_threads":
        return _plot_threads_from_markdown(content)
    if doc_type == "character_state":
        return _characters_from_markdown(content)
    if doc_type == "foreshadowing":
        return _foreshadowing_from_markdown(content)

    category = DOC_TYPE_TO_CATEGORY.get(doc_type, doc_type)
    return [KnowledgeBase(name=doc_type, category=category, body=content)]


def _plot_threads_from_markdown(content: str) -> list[KnowledgeModel]:
    items: list[KnowledgeModel] = []
    for idx, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip().lstrip("-* ").strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped:
            name, progress = stripped.split(":", 1)
        elif "：" in stripped:
            name, progress = stripped.split("：", 1)
        else:
            name, progress = f"plot_thread_{idx}", stripped
        items.append(PlotThreadKnowledge(name=name.strip(), progress=progress.strip(), body=stripped))
    return items


def _characters_from_markdown(content: str) -> list[KnowledgeModel]:
    items: list[KnowledgeModel] = []
    current_name: str | None = None
    current_attrs: dict[str, object] = {}
    current_body_lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if current_name is not None:
                items.append(CharacterKnowledge(
                    name=current_name,
                    attributes=current_attrs,
                    body="\n".join(current_body_lines).strip(),
                ))
            current_name = stripped[3:].strip()
            current_attrs = {}
            current_body_lines = []
        elif stripped.startswith("- ") or stripped.startswith("* "):
            kv = stripped.lstrip("-* ").strip()
            if ":" in kv:
                k, v = kv.split(":", 1)
            elif "：" in kv:
                k, v = kv.split("：", 1)
            else:
                k, v = "", kv
            if k.strip():
                current_attrs[k.strip()] = v.strip()
            current_body_lines.append(stripped)
        elif stripped and not stripped.startswith("#"):
            current_body_lines.append(stripped)
    if current_name is not None:
        items.append(CharacterKnowledge(
            name=current_name,
            attributes=current_attrs,
            body="\n".join(current_body_lines).strip(),
        ))
    return items


def _foreshadowing_from_markdown(content: str) -> list[KnowledgeModel]:
    items: list[KnowledgeModel] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        body = stripped[2:].strip()
        id_match = re.search(r'\[ID:\s*([^\]]+)\]', body)
        fs_id = id_match.group(1).strip() if id_match else f"fs_{len(items)+1:04d}"
        desc = body
        if id_match:
            desc = body.replace(id_match.group(0), "").strip()
        importance = FORESHADOWING_DEFAULT_IMPORTANCE
        imp_match = re.search(r'重要度:\s*(\w+)', body)
        if imp_match:
            importance = imp_match.group(1).strip()
        chapter = 1
        ch_match = re.search(r'埋下章节:\s*(\d+)', body)
        if ch_match:
            chapter = int(ch_match.group(1))
        resolved_chapter = None
        resolved_match = re.search(r'回收章节:\s*(\d+)', body)
        if resolved_match:
            resolved_chapter = int(resolved_match.group(1))
        cancelled_chapter = None
        cancelled_match = re.search(r'作废章节:\s*(\d+)', body)
        if cancelled_match:
            cancelled_chapter = int(cancelled_match.group(1))
        status = FORESHADOWING_STATUS_ACTIVE
        preceding = content[:content.find(stripped)] if content.find(stripped) >= 0 else ""
        if "已回收" in preceding:
            status = FORESHADOWING_STATUS_RESOLVED
        elif "已作废" in preceding:
            status = FORESHADOWING_STATUS_CANCELLED
        items.append(ForeshadowingKnowledge(
            name=fs_id,
            description=desc,
            status=status,
            importance=importance,
            chapter=chapter,
            resolved_chapter=resolved_chapter,
            cancelled_chapter=cancelled_chapter,
        ))
    return items
