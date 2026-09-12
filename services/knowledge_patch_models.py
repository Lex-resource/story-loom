from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from services.knowledge_constants import (
    PATCH_CATEGORY_CHARACTER,
    PATCH_CATEGORY_PLOT_THREAD,
    PATCH_CATEGORY_WORLD_RULE,
)


PatchOperation = Literal["upsert", "merge", "resolve", "cancel", "append_progress"]
PatchCategory = Literal["character", "world_rule", "foreshadowing", "plot_thread"]


class KnowledgePatch(BaseModel):
    category: PatchCategory
    operation: PatchOperation
    name: str
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: Any) -> Any:
        if isinstance(v, str) and v == "character_state":
            return PATCH_CATEGORY_CHARACTER
        if isinstance(v, str) and v == "world_state":
            return PATCH_CATEGORY_WORLD_RULE
        if isinstance(v, str) and v == "plot_threads":
            return PATCH_CATEGORY_PLOT_THREAD
        return v


class KnowledgePatchSet(BaseModel):
    patches: list[KnowledgePatch] = Field(default_factory=list)
    vector_items: list[dict[str, Any]] = Field(default_factory=list)
    raw_issues: list[Any] = Field(default_factory=list)

    @field_validator("patches", mode="before")
    @classmethod
    def filter_invalid_patches(cls, v: Any) -> Any:
        if isinstance(v, list):
            normalized = []
            for item in v:
                if isinstance(item, KnowledgePatch):
                    normalized.append(item)
                elif isinstance(item, dict):
                    if "category" not in item and "doc_type" in item:
                        item = {**item, "category": item["doc_type"]}
                    normalized.append(item)
            return normalized
        return v

    @field_validator("vector_items", mode="before")
    @classmethod
    def normalize_vector_items(cls, v: Any) -> Any:
        if isinstance(v, list):
            normalized = []
            for item in v:
                if isinstance(item, dict):
                    normalized.append(item)
                elif isinstance(item, str) and item.strip():
                    normalized.append({"text": item.strip()})
            return normalized
        return v
