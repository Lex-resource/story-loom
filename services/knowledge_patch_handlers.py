from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Callable

from services.knowledge_constants import (
    FORESHADOWING_STATUS_CANCELLED,
    FORESHADOWING_STATUS_RESOLVED,
    PATCH_CATEGORY_CHARACTER,
    PATCH_CATEGORY_FORESHADOWING,
    PATCH_CATEGORY_PLOT_THREAD,
    PATCH_CATEGORY_WORLD_RULE,
    PLOT_THREAD_PROGRESS_MAX_CHARS,
)
from services.knowledge_patch_models import KnowledgePatch
from services.knowledge_types import (
    CharacterKnowledge,
    ForeshadowingKnowledge,
    KnowledgeModel,
    PlotThreadKnowledge,
    WorldRuleKnowledge,
)

_CHARACTER_RESERVED_KEYS = {
    "attributes", "relationships", "body", "name", "category", "status",
    "importance", "chapter", "chapter_created", "chapter_updated",
    "created_at", "updated_at", "aliases", "description",
}


def normalize_relationship(relationship) -> dict | None:
    if not isinstance(relationship, dict):
        return None
    target = (
        relationship.get("to")
        or relationship.get("entity")
        or relationship.get("name")
        or relationship.get("target")
    )
    if not target:
        return None
    label = (
        relationship.get("label")
        or relationship.get("relation")
        or relationship.get("type")
        or relationship.get("relationship")
        or "相关"
    )
    normalized = {"to": str(target), "label": str(label)}
    description = relationship.get("description") or relationship.get("detail")
    if description:
        normalized["description"] = str(description)
    return normalized


def normalize_relationships(relationships) -> list[dict]:
    if not isinstance(relationships, list):
        return []
    normalized = []
    seen = set()
    for relationship in relationships:
        item = normalize_relationship(relationship)
        if not item:
            continue
        key = (item["to"], item["label"], item.get("description", ""))
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


_RELATIONSHIP_ATTRIBUTE_PATTERNS = (
    re.compile(r"^对(.+?)(?:的)?(?:态度|看法|关系|警告|承诺|怀疑|信任|敌意|好感|评价)$"),
    re.compile(r"^与(.+?)(?:的)?(?:关系|矛盾|合作|联系|交易|约定|冲突)$"),
)

_RELATIONSHIP_TARGET_KEYS = {
    "直属上级": "直属上级",
    "上级": "上级",
    "下属": "下属",
    "搭档": "搭档",
    "同伴": "同伴",
    "师父": "师父",
    "徒弟": "徒弟",
    "盟友": "盟友",
    "敌人": "敌对",
    "仇敌": "敌对",
    "联系人": "联系人",
    "线人": "信息提供",
}

_FORESHADOWING_MATCH_MIN_RATIO = 0.62


def infer_relationships_from_attributes(attributes: dict | None) -> list[dict]:
    if not isinstance(attributes, dict):
        return []

    inferred = []
    for key, value in attributes.items():
        if key == "relationships" or value in (None, "", []):
            continue

        value_text = _stringify_relationship_value(value)
        for pattern in _RELATIONSHIP_ATTRIBUTE_PATTERNS:
            match = pattern.match(str(key))
            if match:
                target = match.group(1).strip()
                if target:
                    inferred.append({
                        "to": target,
                        "label": value_text or key,
                        "description": f"{key}: {value_text}" if value_text else key,
                    })
                break
        else:
            label = _RELATIONSHIP_TARGET_KEYS.get(str(key))
            if label:
                for target in _split_relationship_targets(value):
                    inferred.append({
                        "to": target,
                        "label": label,
                        "description": f"{key}: {value_text}" if value_text else key,
                    })

    return normalize_relationships(inferred)


def relationships_for_attributes(attributes: dict | None) -> list[dict]:
    if not isinstance(attributes, dict):
        return []
    explicit = normalize_relationships(attributes.get("relationships", []))
    rel_map = {
        (relationship.get("to"), relationship.get("label")): relationship
        for relationship in explicit
        if relationship.get("to")
    }
    for relationship in infer_relationships_from_attributes(attributes):
        rel_map.setdefault((relationship["to"], relationship["label"]), relationship)
    return list(rel_map.values())


def _stringify_relationship_value(value) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value if item not in (None, ""))
    if isinstance(value, dict):
        return "，".join(f"{k}: {v}" for k, v in value.items() if v not in (None, ""))
    return str(value).strip()


def _split_relationship_targets(value) -> list[str]:
    if isinstance(value, list):
        candidates = value
    else:
        candidates = re.split(r"[、,，/；;和与]", str(value))
    return [str(candidate).strip() for candidate in candidates if str(candidate).strip()]


def apply_patch(indexed: dict[str, KnowledgeModel], patch: KnowledgePatch, chapter_index: int = 1) -> None:
    handler = PATCH_HANDLERS.get(patch.category)
    if handler is None:
        return
    handler(indexed, patch, chapter_index=chapter_index)


def apply_character(
    indexed: dict[str, KnowledgeModel], patch: KnowledgePatch, chapter_index: int = 1
) -> None:
    item = indexed.get(patch.name) or CharacterKnowledge(name=patch.name)

    nested_attrs = patch.data.get("attributes")
    if isinstance(nested_attrs, dict):
        item.attributes.update(nested_attrs)
    for key, value in patch.data.items():
        if key not in _CHARACTER_RESERVED_KEYS:
            item.attributes[key] = value

    new_relationships = patch.data.get("relationships")
    if new_relationships is None and isinstance(nested_attrs, dict):
        new_relationships = nested_attrs.get("relationships")
    if new_relationships is not None:
        normalized_new_relationships = normalize_relationships(new_relationships)
        if patch.operation == "merge":
            existing_relationships = normalize_relationships(item.attributes.get("relationships", []))
            rel_map = {
                (relationship.get("to"), relationship.get("label")): relationship
                for relationship in existing_relationships
                if relationship.get("to")
            }
            for relationship in normalized_new_relationships:
                rel_map[(relationship["to"], relationship["label"])] = relationship
            item.attributes["relationships"] = list(rel_map.values())
        else:
            item.attributes["relationships"] = normalized_new_relationships

    body = patch.data.get("body")
    if body:
        existing_free = str(item.attributes.get("_free_text", ""))
        if body not in existing_free:
            item.attributes["_free_text"] = f"{existing_free}\n{body}".strip()

    indexed[patch.name] = item


def apply_world_rule(
    indexed: dict[str, KnowledgeModel], patch: KnowledgePatch, chapter_index: int = 1
) -> None:
    item = indexed.get(patch.name) or WorldRuleKnowledge(name=patch.name)

    for key, value in patch.data.items():
        if key not in ("body", "content", "rule_type"):
            item.attributes[key] = value

    if "rule_type" in patch.data:
        item.rule_type = patch.data["rule_type"]

    body = patch.data.get("body") or patch.data.get("content", "")
    if body:
        existing_free = str(item.attributes.get("_free_text", ""))
        if body not in existing_free:
            item.attributes["_free_text"] = f"{existing_free}\n{body}".strip()

    indexed[patch.name] = item


def apply_foreshadowing(
    indexed: dict[str, KnowledgeModel], patch: KnowledgePatch, chapter_index: int = 1
) -> None:
    item_key = _resolve_foreshadowing_key(indexed, patch.name) if patch.operation in {"resolve", "cancel"} else patch.name
    item = indexed.get(item_key)
    is_new = not isinstance(item, ForeshadowingKnowledge)
    if is_new and patch.operation in {"resolve", "cancel"}:
        return
    if is_new:
        item = ForeshadowingKnowledge(name=patch.name, chapter=chapter_index)

    description = patch.data.get("description", "").strip()
    if description:
        if patch.operation == "merge" and item.description and description not in item.description:
            item.description = f"{item.description}\n{description}"
        else:
            item.description = description

    item.importance = patch.data.get("importance", item.importance)
    # 承诺-张力图谱：把债务维度存入 attributes（debt_type/tension/buried_depth）。
    # 无损随 DB data 列往返，供 _due_debt_items 调度排序与提醒标签使用。
    for debt_key in ("debt_type", "tension", "buried_depth"):
        value = patch.data.get(debt_key)
        if value:
            item.attributes[debt_key] = str(value)
    patch_chapter = patch.data.get("chapter")
    if patch_chapter and patch.operation not in {"resolve", "cancel"}:
        item.chapter = int(patch_chapter)
    elif is_new:
        item.chapter = chapter_index

    if patch.operation == "resolve":
        item.status = FORESHADOWING_STATUS_RESOLVED
        item.resolved_chapter = int(patch.data.get("chapter") or chapter_index)
        _record_foreshadowing_resolution(item, patch)
    elif patch.operation == "cancel":
        item.status = FORESHADOWING_STATUS_CANCELLED
        item.cancelled_chapter = int(patch.data.get("chapter") or chapter_index)
    elif patch.operation == "upsert":
        item.status = patch.data.get("status", item.status)

    indexed[item_key if not is_new else patch.name] = item


def _resolve_foreshadowing_key(indexed: dict[str, KnowledgeModel], patch_name: str) -> str:
    if patch_name in indexed and isinstance(indexed[patch_name], ForeshadowingKnowledge):
        return patch_name

    normalized_patch = _normalize_foreshadowing_name(patch_name)
    if not normalized_patch:
        return patch_name

    best_key = patch_name
    best_ratio = 0.0
    for key, value in indexed.items():
        if not isinstance(value, ForeshadowingKnowledge):
            continue
        candidates = [key, value.name, *getattr(value, "aliases", [])]
        for candidate in candidates:
            normalized_candidate = _normalize_foreshadowing_name(candidate)
            if not normalized_candidate:
                continue
            if normalized_candidate == normalized_patch:
                return key
            ratio = SequenceMatcher(None, normalized_patch, normalized_candidate).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_key = key

    return best_key if best_ratio >= _FORESHADOWING_MATCH_MIN_RATIO else patch_name


def _normalize_foreshadowing_name(name: str) -> str:
    text = str(name or "").strip().lower()
    text = re.sub(r"[\s《》“”\"'：:，,。.!！?？、\-—_（）()\[\]【】]", "", text)
    for filler in ("神秘", "真实", "真相", "秘密", "线索", "伏笔", "之谜", "谜团"):
        text = text.replace(filler, "")
    return text


def _record_foreshadowing_resolution(item: ForeshadowingKnowledge, patch: KnowledgePatch) -> None:
    resolution = patch.data.get("resolution") or patch.data.get("resolved_as") or patch.data.get("body")
    if resolution:
        item.attributes["resolution"] = str(resolution)


def apply_plot_thread(
    indexed: dict[str, KnowledgeModel], patch: KnowledgePatch, chapter_index: int = 1
) -> None:
    item = indexed.get(patch.name)
    is_new = not isinstance(item, PlotThreadKnowledge)
    if is_new:
        item = PlotThreadKnowledge(name=patch.name)
        item.chapter_created = chapter_index
    item.chapter_updated = chapter_index

    progress = patch.data.get("progress") or patch.data.get("body") or ""
    if isinstance(progress, str) and len(progress) > PLOT_THREAD_PROGRESS_MAX_CHARS:
        progress = progress[:PLOT_THREAD_PROGRESS_MAX_CHARS - 3] + "..."

    if progress:
        progress_line = f"第{chapter_index}章: {progress}"
        if item.progress and progress_line not in item.progress:
            item.progress = f"{item.progress}\n{progress_line}"
        else:
            item.progress = progress_line

    new_next_step = patch.data.get("next_step")
    if new_next_step:
        item.next_step = new_next_step

    if patch.operation == "resolve":
        item.status = FORESHADOWING_STATUS_RESOLVED
        item.resolved_chapter = int(patch.data.get("chapter") or chapter_index)
    elif patch.operation == "cancel":
        item.status = FORESHADOWING_STATUS_CANCELLED
    elif patch.operation == "upsert":
        item.status = patch.data.get("status", item.status)

    indexed[patch.name] = item


PatchHandler = Callable[[dict[str, KnowledgeModel], KnowledgePatch, int], None]

PATCH_HANDLERS: dict[str, PatchHandler] = {
    PATCH_CATEGORY_CHARACTER: apply_character,
    PATCH_CATEGORY_WORLD_RULE: apply_world_rule,
    PATCH_CATEGORY_FORESHADOWING: apply_foreshadowing,
    PATCH_CATEGORY_PLOT_THREAD: apply_plot_thread,
}


def register_patch_handler(category: str, handler: PatchHandler) -> None:
    PATCH_HANDLERS[category] = handler
