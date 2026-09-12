"""Transactional character card persistence and sparse chapter state."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.characters import (
    CharacterCard,
    CharacterCardChangeRecord,
    CharacterCardSnapshot,
    CharacterChapterState,
)
from services.character_manifest_service import json_checksum, refresh_manifest
from services.character_arc_service import sync_card_arcs
from services.character_relationship_service import sync_card_relationships
from services.character_constants import (
    CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
    CHARACTER_GENERATION_DEFAULT_STATUS,
    CHARACTER_STATUSES,
    CHARACTER_IMPORTANCES,
    CHARACTER_FIRST_CHAPTER,
    CHARACTER_STORYLINE_MAIN,
    normalize_character_status,
)
from services.character_schemas import normalize_aliases, normalize_card_data, normalize_current_state
from services.character_types import CharacterCardUpdate
from services.character_card_serialization import (
    _card_payload,
    _deep_merge_dict,
    _diff_values,
    _has_meaningful_value,
    _merge_card_relationships,
    stable_card_data_for_update,
)

DEFAULT_CHARACTER_PAGE_SIZE = 200
MAX_CHARACTER_PAGE_SIZE = 500


def _apply_page(statement, limit: int | None, offset: int, *, max_limit: int = MAX_CHARACTER_PAGE_SIZE):
    if limit is None:
        return statement
    bounded_limit = min(max(int(limit), 1), max_limit)
    bounded_offset = max(int(offset), 0)
    return statement.limit(bounded_limit).offset(bounded_offset)


async def get_character(db: AsyncSession, project_id, character_id) -> CharacterCard | None:
    result = await db.execute(
        select(CharacterCard).where(
            CharacterCard.project_id == project_id,
            CharacterCard.id == character_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_character_for_update(db: AsyncSession, project_id, character_id) -> CharacterCard | None:
    result = await db.execute(
        select(CharacterCard)
        .where(
            CharacterCard.project_id == project_id,
            CharacterCard.id == character_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def list_characters(
    db: AsyncSession,
    project_id,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[CharacterCard]:
    result = await db.execute(
        _apply_page(
            select(CharacterCard)
            .where(CharacterCard.project_id == project_id)
            .order_by(CharacterCard.importance.desc(), CharacterCard.name, CharacterCard.id),
            limit,
            offset,
        )
    )
    return list(result.scalars().all())


async def update_character_card(
    db: AsyncSession,
    project_id,
    character_id,
    *,
    name: str | None = None,
    card_data: dict[str, Any] | None = None,
    current_state: dict[str, Any] | None = None,
    aliases: list[str] | None = None,
    importance: str | None = None,
    last_appearance: int | None = None,
    status: str | None = None,
    effective_from_chapter: int | None = None,
) -> CharacterCard:
    card = await _get_character_for_update(db, project_id, character_id)
    if card is None:
        raise LookupError("Character card not found")

    before = _card_payload(card)
    if name is not None:
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Character name must not be blank")
        if clean_name != card.name:
            duplicate_result = await db.execute(
                select(CharacterCard).where(
                    CharacterCard.project_id == project_id,
                    CharacterCard.name == clean_name,
                    CharacterCard.id != card.id,
                )
            )
            if duplicate_result.scalar_one_or_none() is not None:
                raise ValueError(f"Character already exists: {clean_name}")
            aliases = list(card.aliases or [])
            if card.name not in aliases:
                aliases.append(card.name)
            card.aliases = normalize_aliases(aliases)
            card.name = clean_name
    if card_data is not None:
        card.card_data = normalize_card_data(card_data)
    if current_state is not None:
        card.current_state = normalize_current_state(current_state)
    if aliases is not None:
        card.aliases = normalize_aliases(aliases)
    if importance is not None:
        clean_importance = str(importance).strip() or card.importance
        if clean_importance not in CHARACTER_IMPORTANCES:
            raise ValueError(f"importance must be one of: {', '.join(CHARACTER_IMPORTANCES)}")
        card.importance = clean_importance
    if last_appearance is not None:
        if last_appearance < 1:
            raise ValueError("last_appearance must be positive")
        card.last_appearance = last_appearance
    if status is not None:
        clean_status = normalize_character_status(status) or card.status
        if clean_status not in CHARACTER_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(CHARACTER_STATUSES)}")
        card.status = clean_status

    if effective_from_chapter is not None and effective_from_chapter < 1:
        raise ValueError("effective_from_chapter must be positive")

    await db.flush()
    after = _card_payload(card)
    changed_fields, patch = _diff_values(before, after)
    if changed_fields:
        snapshot = CharacterCardSnapshot(
            character_id=card.id,
            card_data=before["card_data"],
            current_state=before["current_state"],
            snapshot_metadata=before["metadata"],
            checksum=json_checksum(before),
        )
        db.add(snapshot)
        await db.flush()
        db.add(
            CharacterCardChangeRecord(
                character_id=card.id,
                before_snapshot_id=snapshot.id,
                changed_fields=changed_fields,
                patch=patch,
                effective_from_chapter=effective_from_chapter,
            )
        )
    await sync_card_relationships(
        db,
        card,
        chapter_index=effective_from_chapter or CHARACTER_FIRST_CHAPTER,
    )
    await sync_card_arcs(db, card)
    await refresh_manifest(db, card)
    await db.flush()
    return card


async def create_character_card(
    db: AsyncSession,
    project_id,
    *,
    name: str,
    card_data: dict[str, Any] | None = None,
    current_state: dict[str, Any] | None = None,
    aliases: list[str] | None = None,
    importance: str = CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
    last_appearance: int | None = None,
    status: str = CHARACTER_GENERATION_DEFAULT_STATUS,
) -> CharacterCard:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Character name must not be blank")
    if importance not in CHARACTER_IMPORTANCES:
        raise ValueError(f"importance must be one of: {', '.join(CHARACTER_IMPORTANCES)}")
    status = normalize_character_status(status) or CHARACTER_GENERATION_DEFAULT_STATUS
    if status not in CHARACTER_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(CHARACTER_STATUSES)}")
    if last_appearance is not None and last_appearance < 1:
        raise ValueError("last_appearance must be positive")
    existing = await db.execute(
        select(CharacterCard).where(
            CharacterCard.project_id == project_id,
            CharacterCard.name == clean_name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError(f"Character already exists: {clean_name}")
    card = CharacterCard(
        project_id=project_id,
        name=clean_name,
        aliases=normalize_aliases(aliases),
        card_data=normalize_card_data(card_data),
        current_state=normalize_current_state(current_state),
        importance=importance or CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
        last_appearance=last_appearance,
        status=status or CHARACTER_GENERATION_DEFAULT_STATUS,
    )
    db.add(card)
    await db.flush()
    await sync_card_relationships(db, card, chapter_index=CHARACTER_FIRST_CHAPTER)
    await sync_card_arcs(db, card)
    await refresh_manifest(db, card)
    return card


async def get_state_at_chapter(
    db: AsyncSession,
    character_id,
    chapter_index: int,
    storyline_id: str = CHARACTER_STORYLINE_MAIN,
) -> CharacterChapterState | None:
    result = await db.execute(
        select(CharacterChapterState)
        .where(
            CharacterChapterState.character_id == character_id,
            CharacterChapterState.storyline_id == storyline_id,
            CharacterChapterState.chapter_index <= chapter_index,
        )
        .order_by(CharacterChapterState.chapter_index.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def record_chapter_state_if_changed(
    db: AsyncSession,
    card: CharacterCard,
    *,
    chapter_index: int,
    state_data: dict[str, Any],
    changed_fields: list[str] | None = None,
    storyline_id: str = CHARACTER_STORYLINE_MAIN,
    source_ref: str | None = None,
) -> CharacterChapterState | None:
    normalized = normalize_current_state(state_data)
    checksum = json_checksum(normalized)
    previous = await get_state_at_chapter(db, card.id, chapter_index - 1, storyline_id)
    if previous and previous.checksum == checksum:
        return None

    existing_result = await db.execute(
        select(CharacterChapterState).where(
            CharacterChapterState.character_id == card.id,
            CharacterChapterState.storyline_id == storyline_id,
            CharacterChapterState.chapter_index == chapter_index,
        )
    )
    state = existing_result.scalar_one_or_none()
    if state is None:
        state = CharacterChapterState(
            character_id=card.id,
            storyline_id=storyline_id,
            chapter_index=chapter_index,
            state_data=normalized,
            changed_fields=changed_fields or [],
            checksum=checksum,
            source_ref=source_ref,
        )
        db.add(state)
    else:
        state.state_data = normalized
        state.changed_fields = changed_fields or []
        state.checksum = checksum
        state.source_ref = source_ref
    card.current_state = normalized
    card.last_appearance = chapter_index
    await db.flush()
    await sync_card_relationships(db, card, chapter_index=chapter_index)
    await sync_card_arcs(db, card)
    await refresh_manifest(db, card)
    return state


async def list_character_states(
    db: AsyncSession,
    character_id,
    *,
    storyline_id: str = CHARACTER_STORYLINE_MAIN,
    limit: int | None = None,
    offset: int = 0,
) -> list[CharacterChapterState]:
    result = await db.execute(
        _apply_page(
            select(CharacterChapterState)
            .where(
                CharacterChapterState.character_id == character_id,
                CharacterChapterState.storyline_id == storyline_id,
            )
            .order_by(CharacterChapterState.chapter_index.asc(), CharacterChapterState.id),
            limit,
            offset,
        )
    )
    return list(result.scalars().all())


async def apply_character_card_updates(
    db: AsyncSession,
    project_id,
    *,
    chapter_index: int,
    updates: list[CharacterCardUpdate | dict[str, Any]],
    source_ref: str | None = None,
) -> dict[str, Any]:
    """Apply observed extractor changes and create sparse state rows atomically."""
    cards = await list_characters(db, project_id)
    by_name: dict[str, CharacterCard] = {}
    for card in cards:
        by_name[card.name] = card
        by_name.update({str(alias): card for alias in card.aliases or []})

    changed_cards: list[CharacterCard] = []
    created_cards: list[CharacterCard] = []
    states: list[CharacterChapterState] = []
    unresolved: list[str] = []
    for raw_update in updates:
        update = (
            raw_update
            if isinstance(raw_update, CharacterCardUpdate)
            else CharacterCardUpdate.model_validate(raw_update)
        )
        card = by_name.get(update.character_name)
        if card is None:
            if not _has_meaningful_value(update.card_data_updates):
                unresolved.append(update.character_name)
                continue
            next_card_data = stable_card_data_for_update(update)
            if update.relationships:
                next_card_data["relationships"] = _merge_card_relationships(
                    next_card_data.get("relationships") or [],
                    update.relationships,
                )
            next_state = normalize_current_state(update.state_data or {})
            card = await create_character_card(
                db,
                project_id,
                name=update.character_name,
                card_data=next_card_data,
                current_state=next_state,
                last_appearance=chapter_index,
                status=update.status or CHARACTER_GENERATION_DEFAULT_STATUS,
            )
            by_name[card.name] = card
            by_name.update({str(alias): card for alias in card.aliases or []})
            changed_cards.append(card)
            created_cards.append(card)
            state = await record_chapter_state_if_changed(
                db,
                card,
                chapter_index=chapter_index,
                state_data=next_state,
                changed_fields=list(update.changed_fields or []) or [
                    f"state_data.{key}" for key in next_state
                ],
                source_ref=source_ref,
            )
            if state is not None:
                states.append(state)
            continue

        before_card_payload = _card_payload(card)
        next_card_data = copy.deepcopy(card.card_data or {})
        # Existing stable card data is immutable to chapter extraction. A
        # later change must come through the explicit character-card API.
        stable_card_updates = stable_card_data_for_update(update)
        if stable_card_updates:
            next_card_data = _deep_merge_dict(next_card_data, stable_card_updates)
        if update.relationships:
            next_card_data["relationships"] = _merge_card_relationships(
                next_card_data.get("relationships") or [],
                update.relationships,
            )

        # Canonicalize both sides before merging so Chinese and English aliases
        # cannot survive as two competing facts in the same state document.
        next_state = normalize_current_state(card.current_state or {})
        if update.state_data:
            next_state = _deep_merge_dict(next_state, normalize_current_state(update.state_data))
        if update.relationships:
            next_state["relationship_changes"] = copy.deepcopy(update.relationships)

        changed_fields = list(update.changed_fields or [])
        if not changed_fields:
            changed_fields.extend(
                f"state_data.{key}" for key in update.state_data
            )
            changed_fields.extend(
                f"card_data.{key}" for key in stable_card_updates
            )
            if update.relationships:
                changed_fields.append("card_data.relationships")
        has_state_change = bool(update.state_data or update.relationships or update.status)
        card = await update_character_card(
            db,
            project_id,
            card.id,
            card_data=next_card_data if next_card_data != (card.card_data or {}) else None,
            current_state=next_state if has_state_change else None,
            status=update.status,
            last_appearance=chapter_index,
            effective_from_chapter=chapter_index,
        )
        # A duplicate extractor retry may contain the same observation for the
        # same chapter. Only enqueue a manifest vector when the persisted card
        # actually changed; evidence and state rows have their own idempotency
        # checks, so this keeps the outbox consistent with them.
        if _card_payload(card) != before_card_payload:
            changed_cards.append(card)
        if has_state_change:
            state = await record_chapter_state_if_changed(
                db,
                card,
                chapter_index=chapter_index,
                state_data=next_state,
                changed_fields=changed_fields,
                source_ref=source_ref,
            )
            if state is not None:
                states.append(state)

    # Resolve relationships after all first-seen cards from this chapter exist.
    for card in created_cards:
        await sync_card_relationships(db, card, chapter_index=chapter_index)
        await sync_card_arcs(db, card)
        await refresh_manifest(db, card)

    return {
        "changed_cards": changed_cards,
        "created_cards": created_cards,
        "states": states,
        "unresolved": unresolved,
    }


async def list_character_changes(
    db: AsyncSession,
    character_id,
    *,
    limit: int | None = None,
    offset: int = 0,
) -> list[tuple[CharacterCardChangeRecord, CharacterCardSnapshot]]:
    result = await db.execute(
        _apply_page(
            select(CharacterCardChangeRecord, CharacterCardSnapshot)
            .join(
                CharacterCardSnapshot,
                CharacterCardSnapshot.id == CharacterCardChangeRecord.before_snapshot_id,
            )
            .where(CharacterCardChangeRecord.character_id == character_id)
            .order_by(
                CharacterCardChangeRecord.created_at.desc(),
                CharacterCardChangeRecord.id,
            ),
            limit,
            offset,
        )
    )
    return list(result.all())


async def rollback_character_card(
    db: AsyncSession,
    project_id,
    character_id,
    change_id,
    *,
    effective_from_chapter: int | None = None,
) -> CharacterCard:
    result = await db.execute(
        select(CharacterCardChangeRecord, CharacterCardSnapshot)
        .join(
            CharacterCardSnapshot,
            CharacterCardSnapshot.id == CharacterCardChangeRecord.before_snapshot_id,
        )
        .where(
            CharacterCardChangeRecord.id == change_id,
            CharacterCardChangeRecord.character_id == character_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        raise LookupError("Character card change record not found")
    _change, snapshot = row
    metadata = snapshot.snapshot_metadata or {}
    return await update_character_card(
        db,
        project_id,
        character_id,
        name=metadata.get("name"),
        card_data=copy.deepcopy(snapshot.card_data),
        current_state=copy.deepcopy(snapshot.current_state),
        aliases=copy.deepcopy(metadata.get("aliases", [])),
        importance=metadata.get("importance"),
        last_appearance=metadata.get("last_appearance"),
        status=metadata.get("status"),
        effective_from_chapter=effective_from_chapter,
    )
