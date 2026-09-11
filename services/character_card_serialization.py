"""Pure character-card payload, diff, and merge helpers."""

from __future__ import annotations

import copy
from typing import Any

from models.characters import CharacterCard
from services.character_constants import CHARACTER_RELATIONSHIP_DEFAULT_TYPE
from services.character_types import CharacterCardUpdate


def has_meaningful_value(value: Any) -> bool:
    if isinstance(value, dict):
        return any(has_meaningful_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(has_meaningful_value(item) for item in value)
    return value not in (None, "")


def card_metadata(card: CharacterCard) -> dict[str, Any]:
    return {
        "name": card.name,
        "aliases": copy.deepcopy(card.aliases or []),
        "importance": card.importance,
        "last_appearance": card.last_appearance,
        "status": card.status,
    }


def card_payload(card: CharacterCard) -> dict[str, Any]:
    return {
        "card_data": copy.deepcopy(card.card_data or {}),
        "current_state": copy.deepcopy(card.current_state or {}),
        "metadata": card_metadata(card),
    }


def diff_values(before: Any, after: Any, path: str = "") -> tuple[list[str], dict[str, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        fields: list[str] = []
        patch: dict[str, Any] = {}
        for key in sorted(set(before) | set(after)):
            child_path = f"{path}.{key}" if path else key
            child_fields, child_patch = diff_values(before.get(key), after.get(key), child_path)
            fields.extend(child_fields)
            patch.update(child_patch)
        return fields, patch
    if before == after:
        return [], {}
    return [path], {path: {"old": before, "new": after}}


def deep_merge_dict(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def stable_card_data_for_update(update: CharacterCardUpdate) -> dict[str, Any]:
    """Return stable fields only for trusted first-card bootstrap updates."""
    if update.card_data_authority != "initial":
        return {}
    return copy.deepcopy(update.card_data_updates or {})


def relationship_target(item: dict[str, Any]) -> str:
    return str(
        item.get("target_name")
        or item.get("to")
        or item.get("target")
        or item.get("name")
        or ""
    ).strip()


def merge_card_relationships(
    existing: list[dict[str, Any]],
    updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = [copy.deepcopy(item) for item in existing if isinstance(item, dict)]
    by_key = {
        (
            relationship_target(item),
            str(item.get("relation_type") or item.get("label") or CHARACTER_RELATIONSHIP_DEFAULT_TYPE),
        ): index
        for index, item in enumerate(merged)
        if relationship_target(item)
    }
    for update in updates:
        if not isinstance(update, dict):
            continue
        target = relationship_target(update)
        if not target:
            continue
        key = (
            target,
            str(update.get("relation_type") or update.get("label") or CHARACTER_RELATIONSHIP_DEFAULT_TYPE),
        )
        index = by_key.get(key)
        if index is None:
            by_key[key] = len(merged)
            merged.append(copy.deepcopy(update))
        else:
            merged[index] = deep_merge_dict(merged[index], update)
    return merged


# Compatibility aliases for the service's existing private call sites.
_has_meaningful_value = has_meaningful_value
_card_metadata = card_metadata
_card_payload = card_payload
_diff_values = diff_values
_deep_merge_dict = deep_merge_dict
_relationship_target = relationship_target
_merge_card_relationships = merge_card_relationships
