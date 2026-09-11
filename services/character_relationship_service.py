"""Structured character relationship projection and lookup helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.characters import CharacterCard, CharacterRelationship
from services.character_constants import (
    CHARACTER_FIRST_CHAPTER,
    CHARACTER_RELATIONSHIP_ACTIVE,
    CHARACTER_RELATIONSHIP_DEFAULT_STATUS,
    CHARACTER_RELATIONSHIP_DEFAULT_TYPE,
)


def _relationship_items(card: CharacterCard) -> list[dict[str, Any]]:
    data = card.card_data or {}
    relationships = data.get("relationships") or []
    if not isinstance(relationships, list):
        return []
    return [item for item in relationships if isinstance(item, dict)]


def _target_name(item: dict[str, Any]) -> str:
    return str(
        item.get("target_name")
        or item.get("to")
        or item.get("target")
        or item.get("name")
        or ""
    ).strip()


async def sync_card_relationships(
    db: AsyncSession,
    card: CharacterCard,
    *,
    chapter_index: int = CHARACTER_FIRST_CHAPTER,
) -> list[CharacterRelationship]:
    """Sync resolvable card relationships into the graph-facing table.

    Unresolved names stay in the author-facing card and are intentionally not
    converted into graph edges until the target character card exists.
    """

    cards_result = await db.execute(
        select(CharacterCard).where(CharacterCard.project_id == card.project_id)
    )
    cards = cards_result.scalars().all()
    by_name: dict[str, CharacterCard] = {}
    for candidate in cards:
        by_name[candidate.name] = candidate
        for alias in candidate.aliases or []:
            by_name[str(alias)] = candidate

    existing_result = await db.execute(
        select(CharacterRelationship).where(
            CharacterRelationship.source_character_id == card.id
        )
    )
    existing = {
        (item.target_character_id, item.relation_type): item
        for item in existing_result.scalars().all()
    }
    desired_keys: set[tuple[Any, str]] = set()
    synced: list[CharacterRelationship] = []
    for item in _relationship_items(card):
        target = by_name.get(_target_name(item))
        if target is None or target.id == card.id:
            continue
        relation_type = str(
            item.get("relation_type")
            or item.get("label")
            or item.get("relation")
            or CHARACTER_RELATIONSHIP_DEFAULT_TYPE
        ).strip() or CHARACTER_RELATIONSHIP_DEFAULT_TYPE
        desired_keys.add((target.id, relation_type))
        attributes = dict(item)
        attributes.pop("target_name", None)
        attributes.pop("to", None)
        attributes.pop("target", None)
        attributes.pop("name", None)
        attributes["source_perspective"] = str(
            item.get("source_perspective")
            or item.get("summary")
            or item.get("description")
            or ""
        )
        relationship = existing.get((target.id, relation_type))
        if relationship is None:
            relationship = CharacterRelationship(
                project_id=card.project_id,
                source_character_id=card.id,
                target_character_id=target.id,
                relation_type=relation_type,
                status=str(item.get("status") or CHARACTER_RELATIONSHIP_DEFAULT_STATUS),
                attributes=attributes,
                valid_from_chapter=max(CHARACTER_FIRST_CHAPTER, chapter_index),
            )
            db.add(relationship)
        else:
            relationship.status = str(
                item.get("status") or relationship.status or CHARACTER_RELATIONSHIP_DEFAULT_STATUS
            )
            relationship.attributes = attributes
            relationship.valid_to_chapter = None
        synced.append(relationship)
    for key, relationship in existing.items():
        if key not in desired_keys:
            await db.delete(relationship)
    await db.flush()
    return synced


async def list_card_relationships(
    db: AsyncSession,
    project_id,
    character_id=None,
) -> list[CharacterRelationship]:
    query = select(CharacterRelationship).where(CharacterRelationship.project_id == project_id)
    if character_id is not None:
        query = query.where(
            (CharacterRelationship.source_character_id == character_id)
            | (CharacterRelationship.target_character_id == character_id)
        )
    result = await db.execute(query.order_by(CharacterRelationship.created_at, CharacterRelationship.id))
    return list(result.scalars().all())
