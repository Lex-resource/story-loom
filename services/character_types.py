"""Pydantic contracts shared by character-card agents and API routes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from services.character_constants import (
    CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
    CHARACTER_GENERATION_DEFAULT_STATUS,
    normalize_character_status,
)
from services.character_schemas import CharacterCardData


class GeneratedCharacterCard(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    card_data: CharacterCardData = Field(default_factory=CharacterCardData)
    current_state: dict[str, Any] = Field(default_factory=dict)
    importance: str = CHARACTER_GENERATION_DEFAULT_IMPORTANCE
    status: str = CHARACTER_GENERATION_DEFAULT_STATUS

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> str:
        return normalize_character_status(value) or CHARACTER_GENERATION_DEFAULT_STATUS

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: Any) -> str:
        return str(value or "").strip()


class CharacterCardGenerationResponse(BaseModel):
    characters: list[GeneratedCharacterCard] = Field(default_factory=list)


class CharacterCardUpdate(BaseModel):
    character_name: str
    state_data: dict[str, Any] = Field(default_factory=dict)
    card_data_updates: dict[str, Any] = Field(default_factory=dict)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    changed_fields: list[str] = Field(default_factory=list)
    status: str | None = None
    # Only trusted first-card bootstrap may write stable card data.
    card_data_authority: Literal["extractor", "initial"] = "extractor"

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> str | None:
        return normalize_character_status(value)

    @field_validator("character_name", mode="before")
    @classmethod
    def normalize_character_name(cls, value: Any) -> str:
        return str(value or "").strip()


class CharacterCardExtractionResponse(BaseModel):
    updates: list[CharacterCardUpdate] = Field(default_factory=list)


class CharacterStateResponse(BaseModel):
    id: str
    character_id: str
    storyline_id: str
    chapter_index: int
    state_data: dict[str, Any]
    changed_fields: list[str] = Field(default_factory=list)
    checksum: str
    source_ref: str | None = None


class CharacterChangeResponse(BaseModel):
    id: str
    character_id: str
    before_snapshot_id: str
    changed_fields: list[str] = Field(default_factory=list)
    patch: dict[str, Any] = Field(default_factory=dict)
    effective_from_chapter: int | None = None
    created_at: str | None = None
    before_snapshot: dict[str, Any] | None = None
