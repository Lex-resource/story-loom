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
    WorldRuleKnowledge,
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
            if item.body:
                lines.append("")
                lines.append(item.body)
            for k, v in (item.attributes or {}).items():
                if k in {"relationships", "rule_type", "type"}:
                    continue
                _append_attribute(lines, k, v)
            relationships = relationships_for_attributes(item.attributes)
            if relationships:
                lines.append("")
                lines.append("### 关系")
                for relationship in relationships:
                    description = relationship.get("description", "")
                    suffix = f"：{description}" if description else ""
                    lines.append(f"- {relationship['to']}（{relationship.get('label', '相关')}）{suffix}")
            lines.append("")
        return "\n".join(lines).strip()

    if doc_type == "world_state":
        lines: list[str] = []
        for item in items:
            lines.append(f"## {item.name}")
            if item.body:
                lines.append("")
                lines.append(item.body)
            if isinstance(item, WorldRuleKnowledge) and item.rule_type:
                lines.append("")
                lines.append(f"- **规则类型**: {item.rule_type}")
            for k, v in (item.attributes or {}).items():
                if k in {"rule_type", "type"}:
                    continue
                _append_attribute(lines, k, v)
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


def legacy_json_to_markdown(doc_type: str, content: str) -> str | None:
    """Convert legacy JSON knowledge documents to the author-facing Markdown format."""
    if doc_type not in {"character_state", "world_state"}:
        return None

    try:
        payload = json.loads(content or "")
    except (TypeError, json.JSONDecodeError):
        return None

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return None

    items: list[KnowledgeModel] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            continue

        attributes = raw.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        common = {
            "name": _legacy_text(raw.get("name") or raw.get("title") or f"未命名设定 {index + 1}"),
            "body": _legacy_text(raw.get("body") or raw.get("description") or ""),
            "attributes": attributes,
            "aliases": raw.get("aliases") if isinstance(raw.get("aliases"), list) else [],
            "status": raw.get("status", "active"),
            "importance": raw.get("importance", "medium"),
            "chapter_created": raw.get("chapter_created"),
            "chapter_updated": raw.get("chapter_updated"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }

        if doc_type == "character_state":
            items.append(CharacterKnowledge(**common))
            continue

        rule_type = raw.get("rule_type") or raw.get("type") or attributes.get("rule_type", "")
        items.append(WorldRuleKnowledge(
            **common,
            rule_type=_legacy_text(rule_type),
        ))

    return knowledge_to_markdown(doc_type, items)


def knowledge_from_markdown(doc_type: KnowledgeDocType, content: str) -> list[KnowledgeModel]:
    if not content:
        return []

    if doc_type == "plot_threads":
        return _plot_threads_from_markdown(content)
    if doc_type == "character_state":
        return _characters_from_markdown(content)
    if doc_type == "world_state":
        return _world_rules_from_markdown(content)
    if doc_type == "foreshadowing":
        return _foreshadowing_from_markdown(content)

    category = DOC_TYPE_TO_CATEGORY.get(doc_type, doc_type)
    return [KnowledgeBase(name=doc_type, category=category, body=content)]


def _legacy_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


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
    current_section = ""

    def finish_current() -> None:
        nonlocal current_name, current_attrs, current_body_lines
        if current_name is not None:
            items.append(CharacterKnowledge(
                name=current_name,
                attributes=current_attrs,
                body="\n".join(current_body_lines).strip(),
            ))

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            finish_current()
            current_name = stripped[3:].strip()
            current_attrs = {}
            current_body_lines = []
            current_section = ""
        elif stripped.startswith("### "):
            current_section = stripped[4:].strip()
        elif stripped.startswith("- ") or stripped.startswith("* "):
            value = _strip_markdown_bullet(stripped)
            if current_section == "关系":
                relationship = _parse_relationship(value)
                if relationship:
                    current_attrs.setdefault("relationships", []).append(relationship)
                    continue
            key, value = _parse_markdown_field(value)
            if key:
                current_attrs[key] = value
            else:
                current_body_lines.append(value)
        elif stripped and not stripped.startswith("#"):
            current_body_lines.append(stripped)
    finish_current()
    return items


def _world_rules_from_markdown(content: str) -> list[KnowledgeModel]:
    items: list[KnowledgeModel] = []
    current_name: str | None = None
    current_attrs: dict[str, object] = {}
    current_body_lines: list[str] = []

    def finish_current() -> None:
        nonlocal current_name, current_attrs, current_body_lines
        if current_name is None:
            return
        rule_type = str(
            current_attrs.pop("规则类型", "")
            or current_attrs.pop("rule_type", "")
            or current_attrs.pop("type", "")
        )
        items.append(WorldRuleKnowledge(
            name=current_name,
            rule_type=rule_type,
            attributes=current_attrs,
            body="\n".join(current_body_lines).strip(),
        ))

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            finish_current()
            current_name = stripped[3:].strip()
            current_attrs = {}
            current_body_lines = []
        elif stripped.startswith("### "):
            continue
        elif stripped.startswith("- ") or stripped.startswith("* "):
            key, value = _parse_markdown_field(_strip_markdown_bullet(stripped))
            if key:
                current_attrs[key] = value
            elif value:
                current_body_lines.append(value)
        elif stripped.startswith("**"):
            key, value = _parse_markdown_field(stripped)
            if key:
                current_attrs[key] = value
        elif stripped and not stripped.startswith("#"):
            current_body_lines.append(stripped)
    finish_current()
    return items


def _append_attribute(lines: list[str], key: str, value: object) -> None:
    if isinstance(value, list):
        lines.append(f"### {key}")
        for item in value:
            if isinstance(item, dict):
                pairs = "；".join(f"{sub_key}: {sub_value}" for sub_key, sub_value in item.items())
                lines.append(f"- {pairs}")
            else:
                lines.append(f"- {item}")
        return
    if isinstance(value, dict):
        lines.append(f"### {key}")
        for sub_key, sub_value in value.items():
            lines.append(f"- **{sub_key}**: {sub_value}")
        return
    lines.append(f"- **{key}**: {value}")


def _parse_markdown_field(value: str) -> tuple[str, str]:
    bold_match = re.match(r"^\*\*(.+?)\*\*\s*[:：]\s*(.*)$", value)
    if bold_match:
        return bold_match.group(1).strip(), bold_match.group(2).strip()
    for separator in ("：", ":"):
        if separator in value:
            key, field_value = value.split(separator, 1)
            return key.strip(), field_value.strip()
    return "", value.strip()


def _strip_markdown_bullet(value: str) -> str:
    return re.sub(r"^[-*]\s+", "", value.strip())


def _parse_relationship(value: str) -> dict[str, str] | None:
    match = re.match(r"^(.+?)（(.+?)）(?:\s*[:：]\s*(.*))?$", value)
    if not match:
        return None
    relationship = {"to": match.group(1).strip(), "label": match.group(2).strip()}
    if match.group(3):
        relationship["description"] = match.group(3).strip()
    return relationship


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
