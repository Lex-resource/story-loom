from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field, field_validator

from services.document_constants import (
    DOC_TYPE_ACT_OUTLINE,
    DOC_TYPE_CHARACTER_STATE,
    DOC_TYPE_FORESHADOWING,
    DOC_TYPE_GLOBAL_OUTLINE,
    DOC_TYPE_PLOT_THREADS,
    DOC_TYPE_WORLD_STATE,
)
from services.knowledge_constants import (
    FORESHADOWING_DEFAULT_IMPORTANCE,
    FORESHADOWING_STATUS_ACTIVE,
    PATCH_CATEGORY_CHARACTER,
    PATCH_CATEGORY_FORESHADOWING,
    PATCH_CATEGORY_PLOT_THREAD,
    PATCH_CATEGORY_WORLD_RULE,
)


KnowledgeDocType = Literal[
    "character_state",
    "world_state",
    "foreshadowing",
    "plot_threads",
    "global_outline",
    "act_outline",
]


class KnowledgeBase(BaseModel):
    name: str
    category: str
    body: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    status: str = FORESHADOWING_STATUS_ACTIVE
    importance: str = FORESHADOWING_DEFAULT_IMPORTANCE
    chapter_created: int | None = None
    chapter_updated: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("name", "category", "body", "status", "importance", mode="before")
    @classmethod
    def coerce_string_fields(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value)


class CharacterKnowledge(KnowledgeBase):
    category: Literal["character"] = "character"


class WorldRuleKnowledge(KnowledgeBase):
    category: Literal["world_rule"] = "world_rule"
    rule_type: str = ""


class ForeshadowingKnowledge(KnowledgeBase):
    category: Literal["foreshadowing"] = "foreshadowing"
    description: str = ""
    chapter: int = 1
    resolved_chapter: int | None = None
    cancelled_chapter: int | None = None


class PlotThreadKnowledge(KnowledgeBase):
    category: Literal["plot_thread"] = "plot_thread"
    progress: str = ""
    next_step: str = ""
    resolved_chapter: int | None = None


KnowledgeModel = Union[
    CharacterKnowledge,
    WorldRuleKnowledge,
    ForeshadowingKnowledge,
    PlotThreadKnowledge,
    KnowledgeBase,
]


DOC_TYPE_TO_CATEGORY = {
    DOC_TYPE_CHARACTER_STATE: PATCH_CATEGORY_CHARACTER,
    DOC_TYPE_WORLD_STATE: PATCH_CATEGORY_WORLD_RULE,
    DOC_TYPE_FORESHADOWING: PATCH_CATEGORY_FORESHADOWING,
    DOC_TYPE_PLOT_THREADS: PATCH_CATEGORY_PLOT_THREAD,
    DOC_TYPE_GLOBAL_OUTLINE: DOC_TYPE_GLOBAL_OUTLINE,
    DOC_TYPE_ACT_OUTLINE: DOC_TYPE_ACT_OUTLINE,
}

CATEGORY_TO_DOC_TYPE = {
    category: doc_type for doc_type, category in DOC_TYPE_TO_CATEGORY.items()
}
