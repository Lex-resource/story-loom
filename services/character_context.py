"""Bounded, role-specific character context for Planner and Writer."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.characters import CharacterCard, CharacterManifest, CharacterRelationship
from services.character_card_service import get_state_at_chapter
from services.character_constants import (
    CHARACTER_CONTEXT_MAX_MANIFESTS,
    CHARACTER_CONTEXT_NO_PRIOR_CHAPTER,
    CHARACTER_STATUS_UNKNOWN,
)
from services.character_manifest_service import list_project_manifests
from services.context_compaction import compact_json, context_budget_for

async def build_planner_manifest_context(
    db: AsyncSession,
    project_id,
) -> str:
    """Return only deterministic, compact manifests for chapter planning."""
    manifests = await list_project_manifests(
        db,
        project_id,
        limit=CHARACTER_CONTEXT_MAX_MANIFESTS,
    )
    if not manifests:
        return ""
    payload = {
        "characters": [manifest.data or {} for manifest in manifests],
        "read_only": True,
    }
    return compact_json(
        payload,
        context_budget_for("planner").manifest_chars,
        label="character_manifest",
    )


def _matches_selected_name(card: CharacterCard, names: set[str]) -> bool:
    candidates = {card.name, *(str(alias) for alias in card.aliases or [])}
    return bool(candidates & names)


def _relationship_is_visible_at(relationship: CharacterRelationship, chapter_index: int) -> bool:
    starts_at = relationship.valid_from_chapter
    ends_at = relationship.valid_to_chapter
    return (starts_at is None or starts_at <= chapter_index) and (
        ends_at is None or ends_at >= chapter_index
    )


async def build_writer_character_context(
    db: AsyncSession,
    project_id,
    chapter_index: int,
    character_names: list[str] | None,
) -> str:
    """Load full cards for selected characters without exposing future state."""
    selected_names = {
        str(name).strip()
        for name in character_names or []
        if str(name).strip()
    }
    if not selected_names:
        return ""

    card_result = await db.execute(
        select(CharacterCard)
        .where(CharacterCard.project_id == project_id)
        .order_by(CharacterCard.name)
    )
    cards = [card for card in card_result.scalars().all() if _matches_selected_name(card, selected_names)]
    if not cards:
        return ""

    prior_chapter = max(CHARACTER_CONTEXT_NO_PRIOR_CHAPTER, chapter_index - 1)
    selected_ids = {card.id for card in cards}
    selected_payload: list[dict[str, Any]] = []
    for card in cards:
        state = await get_state_at_chapter(db, card.id, prior_chapter)
        is_future_card = card.last_appearance is not None and card.last_appearance > prior_chapter
        historical_state = state.state_data if state is not None else (
            card.current_state if not is_future_card else {}
        )
        selected_payload.append({
            "character_id": str(card.id),
            "name": card.name,
            "aliases": list(card.aliases or []),
            "importance": card.importance,
            "status": card.status if not is_future_card else CHARACTER_STATUS_UNKNOWN,
            "last_appearance": card.last_appearance if not is_future_card else None,
            "card_data": card.card_data or {},
            "state_at_previous_chapter": historical_state or {},
        })

    relationship_result = await db.execute(
        select(CharacterRelationship).where(
            CharacterRelationship.project_id == project_id,
            or_(
                CharacterRelationship.valid_from_chapter.is_(None),
                CharacterRelationship.valid_from_chapter <= prior_chapter,
            ),
            or_(
                CharacterRelationship.valid_to_chapter.is_(None),
                CharacterRelationship.valid_to_chapter >= prior_chapter,
            ),
            or_(
                CharacterRelationship.source_character_id.in_(selected_ids),
                CharacterRelationship.target_character_id.in_(selected_ids),
            ),
        )
    )
    relationships = [
        relationship
        for relationship in relationship_result.scalars().all()
        if _relationship_is_visible_at(relationship, prior_chapter)
    ]
    all_ids = selected_ids | {
        relationship.source_character_id for relationship in relationships
    } | {
        relationship.target_character_id for relationship in relationships
    }
    name_result = await db.execute(
        select(CharacterCard.id, CharacterCard.name).where(CharacterCard.id.in_(all_ids))
    )
    names_by_id = {character_id: name for character_id, name in name_result.all()}
    relationship_payload = [
        {
            "source": names_by_id.get(item.source_character_id, str(item.source_character_id)),
            "target": names_by_id.get(item.target_character_id, str(item.target_character_id)),
            "relation_type": item.relation_type,
            "status": item.status,
            "attributes": item.attributes or {},
            "valid_from_chapter": item.valid_from_chapter,
            "valid_to_chapter": item.valid_to_chapter,
        }
        for item in relationships
    ]

    neighbor_ids = all_ids - selected_ids
    neighbor_payload: list[dict[str, Any]] = []
    if neighbor_ids:
        manifest_result = await db.execute(
            select(CharacterManifest).where(
                CharacterManifest.character_id.in_(neighbor_ids),
            )
        )
        for manifest in manifest_result.scalars().all():
            data = manifest.data or {}
            neighbor_payload.append({
                "character_id": str(manifest.character_id),
                "name": data.get("name") or names_by_id.get(manifest.character_id, ""),
                "role_summary": data.get("role_summary", ""),
                "status": data.get("status", ""),
                "current_stage": data.get("current_stage", ""),
            })

    payload = {
        "selected_characters": selected_payload,
        "direct_relationship_neighbors": neighbor_payload,
        "relationships": relationship_payload,
        "chapter_context": prior_chapter,
    }
    return compact_json(
        payload,
        context_budget_for("writer").character_chars,
        label="character_cards",
    )


async def build_extractor_character_context(
    db: AsyncSession,
    project_id,
    chapter_index: int,
    character_names: list[str] | None,
    chapter_outline: dict[str, Any] | None = None,
    global_outline: dict[str, Any] | None = None,
) -> str:
    """Build context for first-card creation and later state updates."""
    selected_names = {
        str(name).strip()
        for name in character_names or []
        if str(name).strip()
    }
    if not selected_names:
        return ""

    card_result = await db.execute(
        select(CharacterCard)
        .where(CharacterCard.project_id == project_id)
        .order_by(CharacterCard.name)
    )
    cards = list(card_result.scalars().all())
    existing_cards = [card for card in cards if _matches_selected_name(card, selected_names)]
    existing_names = {
        candidate
        for card in existing_cards
        for candidate in (card.name, *(str(alias) for alias in card.aliases or []))
    }
    new_names = sorted(selected_names - existing_names)

    existing_context: dict[str, Any] = {}
    if existing_cards:
        raw_context = await build_writer_character_context(
            db,
            project_id,
            chapter_index,
            [card.name for card in existing_cards],
        )
        try:
            existing_context = json.loads(raw_context) if raw_context else {}
        except json.JSONDecodeError:
            existing_context = {}

    outline_context = {}
    if isinstance(chapter_outline, dict):
        for key in ("title", "summary", "characters_involved", "required_changes", "end_state"):
            if chapter_outline.get(key) not in (None, "", [], {}):
                outline_context[key] = chapter_outline[key]

    global_character_hints: list[dict[str, Any]] = []
    if isinstance(global_outline, dict):
        raw_characters = (
            global_outline.get("主要人物")
            or global_outline.get("主要角色")
            or global_outline.get("characters")
            or []
        )
        if isinstance(raw_characters, list):
            for item in raw_characters:
                if not isinstance(item, dict):
                    continue
                name = str(
                    item.get("name")
                    or item.get("姓名")
                    or item.get("名字")
                    or item.get("角色名")
                    or ""
                ).strip()
                if name in selected_names:
                    global_character_hints.append(item)

    return _json_text({
        **existing_context,
        "chapter_context": max(0, chapter_index - 1),
        "new_character_candidates": [
            {"name": name, "card_exists": False}
            for name in new_names
        ],
        "chapter_outline": outline_context,
        "global_character_hints": global_character_hints,
        "read_only": True,
    })
