"""API contracts for independent character branches."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from services.character_constants import (
    CHARACTER_BRANCH_DEFAULT_CHAPTER_COUNT,
    CHARACTER_BRANCH_MAX_GENERATION_BATCH,
    CHARACTER_BRANCH_MAX_CHAPTER_COUNT,
    CHARACTER_BRANCH_MAX_TITLE_LENGTH,
)


class CreateCharacterBranchRequest(BaseModel):
    arc_id: str | None = None
    title: str | None = Field(default=None, max_length=CHARACTER_BRANCH_MAX_TITLE_LENGTH)
    anchor_main_chapter: int | None = Field(default=None, ge=1)
    target_chapters: int = Field(
        default=CHARACTER_BRANCH_DEFAULT_CHAPTER_COUNT,
        ge=1,
        le=CHARACTER_BRANCH_MAX_CHAPTER_COUNT,
    )
    user_request: str = ""
    generation_config: dict[str, Any] = Field(default_factory=dict)
    auto_discovered: bool = False

    @field_validator("user_request", mode="before")
    @classmethod
    def normalize_user_request(cls, value: Any) -> str:
        return str(value or "").strip()


class GenerateCharacterBranchRequest(BaseModel):
    chapters: int = Field(default=1, ge=1, le=CHARACTER_BRANCH_MAX_GENERATION_BATCH)
    continue_generation: bool = True
    user_request: str | None = None


class CharacterBranchSettingsRequest(BaseModel):
    auto_discovery_enabled: bool = False


class EditCharacterBranchChapterRequest(BaseModel):
    title: str = Field(min_length=1, max_length=CHARACTER_BRANCH_MAX_TITLE_LENGTH)
    content: str = ""


class BranchCandidateResponse(BaseModel):
    character_id: str
    character_name: str
    anchor_main_chapter: int
    arc_ids: list[str] = Field(default_factory=list)
    reason: str
