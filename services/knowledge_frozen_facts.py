from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from services import living_docs
from services.knowledge_constants import (
    PATCH_CATEGORY_CHARACTER,
    PATCH_CATEGORY_WORLD_RULE,
)
from services.knowledge_patch_models import KnowledgePatch, KnowledgePatchSet
from services.knowledge_types import (
    CATEGORY_TO_DOC_TYPE,
    CharacterKnowledge,
    KnowledgeModel,
    WorldRuleKnowledge,
)


FROZEN_FACT_CATEGORY = "frozen_fact"
FROZEN_FACT_SEVERITY = "high"

# 真正不可变更的显式锁：任何字段改动都算篡改。
_FROZEN_STATUS_VALUES = {"frozen", "locked", "immutable", "已冻结", "锁定", "不可覆写"}
# 「已证实」不等于「不可演进」——已证实法则只在核心表述(body)被改写时才算矛盾，
# 其描述/属性(如 eta、位置)随剧情推进正常更新，不应触发冻结拦截。
_CONFIRMED_STATUS_VALUES = {"confirmed", "已确认"}
_FROZEN_ATTR_KEYS = {"frozen", "locked", "immutable", "不可覆写", "冻结", "锁定"}
_FROZEN_FIELDS_KEYS = {"frozen_fields", "locked_fields", "immutable_fields", "不可覆写字段", "冻结字段", "锁定字段"}
_DEATH_KEYS = {"是否存活", "生死状态", "状态", "生命状态", "存活状态"}
_DEAD_VALUES = {"死亡", "已死亡", "确认死亡", "阵亡", "dead", "deceased"}
_ALIVE_VALUES = {"存活", "活着", "复活", "未死", "alive", "living", "revived"}


async def find_frozen_fact_violations(
    project_id: str,
    patch_set: KnowledgePatchSet,
    db: AsyncSession,
) -> list[dict[str, Any]]:
    existing_by_category: dict[str, dict[str, KnowledgeModel]] = {}
    for patch in patch_set.patches:
        if patch.category in existing_by_category:
            continue
        doc_type = CATEGORY_TO_DOC_TYPE.get(patch.category)
        if not doc_type:
            continue
        items = await living_docs.read_knowledge(project_id, doc_type, db)
        existing_by_category[patch.category] = {item.name: item for item in items}
    return frozen_fact_violations_for_patches(existing_by_category, patch_set.patches)


def frozen_fact_violations_for_patches(
    existing_by_category: dict[str, dict[str, KnowledgeModel]],
    patches: Iterable[KnowledgePatch],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for patch in patches:
        item = existing_by_category.get(patch.category, {}).get(patch.name)
        if not item:
            continue
        issues.extend(_violations_for_patch(item, patch))
    return issues


def _violations_for_patch(item: KnowledgeModel, patch: KnowledgePatch) -> list[dict[str, Any]]:
    if patch.operation in {"append_progress", "resolve", "cancel"}:
        return []

    issues: list[dict[str, Any]] = []
    changed_fields = _patch_field_names(patch)
    frozen_fields = _frozen_fields(item)

    if _is_item_frozen(item) and changed_fields:
        issues.append(_issue(
            item,
            patch,
            f"试图修改已冻结/已确认的核心设定《{item.name}》。",
            fields=sorted(changed_fields),
        ))
    elif _is_confirmed_world_rule(item) and "body" in changed_fields:
        issues.append(_issue(
            item,
            patch,
            f"试图改写已证实法则《{item.name}》的核心表述（body）。",
            fields=["body"],
        ))

    touched_frozen_fields = changed_fields & frozen_fields
    if touched_frozen_fields:
        issues.append(_issue(
            item,
            patch,
            f"试图修改《{item.name}》的不可覆写字段：{', '.join(sorted(touched_frozen_fields))}。",
            fields=sorted(touched_frozen_fields),
        ))

    if isinstance(item, CharacterKnowledge):
        death_issue = _confirmed_death_violation(item, patch)
        if death_issue:
            issues.append(death_issue)

    return _dedupe_issues(issues)


def _is_item_frozen(item: KnowledgeModel) -> bool:
    status = str(getattr(item, "status", "") or "").strip().lower()
    if status in _FROZEN_STATUS_VALUES:
        return True
    attrs = getattr(item, "attributes", {}) or {}
    return any(_truthy(attrs.get(key)) for key in _FROZEN_ATTR_KEYS)


def _is_confirmed_world_rule(item: KnowledgeModel) -> bool:
    if not isinstance(item, WorldRuleKnowledge):
        return False
    if str(item.rule_type).strip().lower() == "confirmed":
        return True
    status = str(getattr(item, "status", "") or "").strip().lower()
    return status in _CONFIRMED_STATUS_VALUES


def _frozen_fields(item: KnowledgeModel) -> set[str]:
    attrs = getattr(item, "attributes", {}) or {}
    fields: set[str] = set()
    for key in _FROZEN_FIELDS_KEYS:
        fields.update(_as_string_set(attrs.get(key)))
    return fields


def _patch_field_names(patch: KnowledgePatch) -> set[str]:
    fields = set()
    nested_attrs = patch.data.get("attributes")
    if isinstance(nested_attrs, dict):
        fields.update(str(key) for key in nested_attrs)
    fields.update(
        str(key)
        for key in patch.data
        if key not in {"attributes", "chapter", "relationships"}
    )
    return fields


def _confirmed_death_violation(item: CharacterKnowledge, patch: KnowledgePatch) -> dict[str, Any] | None:
    existing_attrs = item.attributes or {}
    if not any(_contains_any(existing_attrs.get(key), _DEAD_VALUES) for key in _DEATH_KEYS):
        return None

    patch_attrs = {}
    nested_attrs = patch.data.get("attributes")
    if isinstance(nested_attrs, dict):
        patch_attrs.update(nested_attrs)
    patch_attrs.update({key: value for key, value in patch.data.items() if key not in {"attributes", "relationships"}})

    changed_to_alive = [
        key for key in _DEATH_KEYS
        if key in patch_attrs and _contains_any(patch_attrs.get(key), _ALIVE_VALUES)
    ]
    if not changed_to_alive:
        return None
    return _issue(
        item,
        patch,
        f"试图把已确认死亡角色《{item.name}》改为存活/复活状态。",
        fields=sorted(changed_to_alive),
    )


def _issue(
    item: KnowledgeModel,
    patch: KnowledgePatch,
    description: str,
    *,
    fields: list[str],
) -> dict[str, Any]:
    return {
        "category": FROZEN_FACT_CATEGORY,
        "severity": FROZEN_FACT_SEVERITY,
        "description": description,
        "doc_type": CATEGORY_TO_DOC_TYPE.get(patch.category, patch.category),
        "name": item.name,
        "operation": patch.operation,
        "fields": fields,
    }


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for issue in issues:
        key = (issue.get("category"), issue.get("name"), issue.get("description"), tuple(issue.get("fields") or []))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def _as_string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {part.strip() for part in value.replace("，", ",").replace("、", ",").split(",") if part.strip()}
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return {str(value).strip()} if str(value).strip() else set()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是", "已冻结", "锁定", "不可覆写", "frozen", "locked"}


def _contains_any(value: Any, candidates: set[str]) -> bool:
    text = str(value or "").strip().lower()
    return any(candidate.lower() in text for candidate in candidates)
