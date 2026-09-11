"""Validation and normalization for author-facing character cards."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.character_constants import CHARACTER_STATE_KEY_ALIASES


class CharacterCardData(BaseModel):
    """Flexible card contract with known sections and forward-compatible extras."""

    model_config = ConfigDict(extra="allow")

    identity: dict[str, Any] = Field(default_factory=dict)
    appearance: dict[str, Any] = Field(default_factory=dict)
    personality: dict[str, Any] = Field(default_factory=dict)
    background: dict[str, Any] = Field(default_factory=dict)
    abilities: dict[str, Any] = Field(default_factory=dict)
    speech_style: dict[str, Any] = Field(default_factory=dict)
    behavior_patterns: dict[str, Any] = Field(default_factory=dict)
    knowledge_boundary: dict[str, Any] = Field(default_factory=dict)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    growth_route: dict[str, Any] = Field(default_factory=dict)
    main_arc: dict[str, Any] = Field(default_factory=dict)
    side_arcs: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)

    @field_validator(
        "identity",
        "appearance",
        "personality",
        "background",
        "abilities",
        "speech_style",
        "behavior_patterns",
        "knowledge_boundary",
        "growth_route",
        "main_arc",
        mode="before",
    )
    @classmethod
    def coerce_section_objects(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"items": value}
        return {"value": value}

    @field_validator("relationships", "side_arcs", mode="before")
    @classmethod
    def coerce_item_lists(cls, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        result: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                result.append(item)
            elif item not in (None, ""):
                result.append({"summary": str(item)})
        return result

    @field_validator("constraints", mode="before")
    @classmethod
    def coerce_constraints(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        return [str(item).strip() for item in value if str(item).strip()]


def normalize_card_data(value: Any) -> dict[str, Any]:
    """Normalize a card while retaining unknown extension fields."""

    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("card_data must be a JSON object")
    return CharacterCardData.model_validate(value).model_dump(mode="json")


def normalize_aliases(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("aliases must be a JSON array")
    return [str(item).strip() for item in value if str(item).strip()]


def normalize_current_state(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("current_state must be a JSON object")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        canonical_key = CHARACTER_STATE_KEY_ALIASES.get(str(key), str(key))
        # Dict insertion order reflects the extractor's update order. The
        # latest alias wins when old and new representations coexist.
        normalized[canonical_key] = item
    return normalized
