"""Character-card, manifest, relationship, and sparse-state endpoints."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from agents.character_card_agent import CharacterCardAgent
from agents.constants import NOVEL_FORMAT_LONG_WEBNOVEL
from database import get_db
from models.characters import CharacterCard, CharacterManifest
from models.novel import Novel
from routers._common import validate_project_id
from services.character_card_service import (
    DEFAULT_CHARACTER_PAGE_SIZE,
    MAX_CHARACTER_PAGE_SIZE,
    create_character_card,
    get_character,
    get_state_at_chapter,
    list_character_changes,
    list_character_states,
    list_characters,
    rollback_character_card,
    update_character_card,
)
from services.character_constants import (
    CHARACTER_GENERATION_MAX_BATCH_SIZE,
    CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
    CHARACTER_GENERATION_DEFAULT_STATUS,
    CHARACTER_FIRST_CHAPTER,
    CHARACTER_STORYLINE_MAIN,
)
from services.character_manifest_service import (
    list_project_manifests,
    refresh_manifest,
    refresh_project_manifests,
)
from services.character_relationship_service import list_card_relationships, sync_card_relationships
from services.character_vector_service import enqueue_character_manifest_vectors
from services.character_types import CharacterChangeResponse


router = APIRouter()


class CharacterHint(BaseModel):
    name: str
    role: str = ""
    summary: str = ""
    relationships: list[dict[str, Any]] = Field(default_factory=list)


class GenerateCharactersRequest(BaseModel):
    names: list[str] = Field(default_factory=list)
    character_hints: list[CharacterHint] = Field(default_factory=list)
    user_hints: str = ""


class UpdateCharacterCardRequest(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    card_data: dict[str, Any] | None = None
    current_state: dict[str, Any] | None = None
    importance: str | None = None
    last_appearance: int | None = Field(default=None, ge=CHARACTER_FIRST_CHAPTER)
    status: str | None = None
    effective_from_chapter: int | None = Field(default=None, ge=CHARACTER_FIRST_CHAPTER)


class RollbackCharacterCardRequest(BaseModel):
    effective_from_chapter: int | None = Field(default=None, ge=CHARACTER_FIRST_CHAPTER)


def _project_uuid(project_id: str) -> uuid.UUID:
    return validate_project_id(project_id)


def _serialize_manifest(manifest: CharacterManifest | None) -> dict[str, Any] | None:
    if manifest is None:
        return None
    return {
        "id": str(manifest.id),
        "project_id": str(manifest.project_id),
        "character_id": str(manifest.character_id),
        "data": copy.deepcopy(manifest.data or {}),
        "checksum": manifest.checksum,
        "is_read_only": bool(manifest.is_read_only),
        "generated_at": manifest.generated_at.isoformat() if manifest.generated_at else None,
        "updated_at": manifest.updated_at.isoformat() if manifest.updated_at else None,
    }


def _serialize_card(card: CharacterCard, manifest: CharacterManifest | None = None) -> dict[str, Any]:
    return {
        "id": str(card.id),
        "project_id": str(card.project_id),
        "name": card.name,
        "aliases": copy.deepcopy(card.aliases or []),
        "card_data": copy.deepcopy(card.card_data or {}),
        "current_state": copy.deepcopy(card.current_state or {}),
        "importance": card.importance,
        "last_appearance": card.last_appearance,
        "status": card.status,
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "updated_at": card.updated_at.isoformat() if card.updated_at else None,
        "manifest": _serialize_manifest(manifest),
    }


def _serialize_state(state) -> dict[str, Any]:
    return {
        "id": str(state.id),
        "character_id": str(state.character_id),
        "storyline_id": state.storyline_id,
        "chapter_index": state.chapter_index,
        "state_data": copy.deepcopy(state.state_data or {}),
        "changed_fields": list(state.changed_fields or []),
        "checksum": state.checksum,
        "source_ref": state.source_ref,
        "created_at": state.created_at.isoformat() if state.created_at else None,
    }


def _serialize_change(change, snapshot) -> dict[str, Any]:
    return CharacterChangeResponse(
        id=str(change.id),
        character_id=str(change.character_id),
        before_snapshot_id=str(change.before_snapshot_id),
        changed_fields=list(change.changed_fields or []),
        patch=copy.deepcopy(change.patch or {}),
        effective_from_chapter=change.effective_from_chapter,
        created_at=change.created_at.isoformat() if change.created_at else None,
        before_snapshot={
            "id": str(snapshot.id),
            "card_data": copy.deepcopy(snapshot.card_data or {}),
            "current_state": copy.deepcopy(snapshot.current_state or {}),
            "metadata": copy.deepcopy(snapshot.snapshot_metadata or {}),
            "checksum": snapshot.checksum,
            "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
        },
    ).model_dump()


def _outline_character_hints(outline: Any) -> list[dict[str, Any]]:
    if not isinstance(outline, dict):
        return []
    raw = outline.get("主要人物") or outline.get("主要角色") or outline.get("characters") or []
    if not isinstance(raw, list):
        return []
    hints: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            name = item.strip()
            if name:
                hints.append({"name": name})
            continue
        if not isinstance(item, dict):
            continue
        name = str(
            item.get("name")
            or item.get("姓名")
            or item.get("名字")
            or item.get("角色名")
            or ""
        ).strip()
        if name:
            hints.append({
                "name": name,
                "role": str(item.get("role") or item.get("角色") or ""),
                "summary": str(item.get("summary") or item.get("简述") or item.get("动机") or ""),
                "relationships": item.get("relationships") if isinstance(item.get("relationships"), list) else [],
            })
    return hints


async def _ensure_manifest(db, card: CharacterCard) -> CharacterManifest:
    result = await db.execute(
        select(CharacterManifest).where(CharacterManifest.character_id == card.id)
    )
    manifest = result.scalar_one_or_none()
    if manifest is None:
        manifest = await refresh_manifest(db, card)
    return manifest


async def _get_manifest(db, card: CharacterCard) -> CharacterManifest | None:
    result = await db.execute(
        select(CharacterManifest).where(CharacterManifest.character_id == card.id)
    )
    return result.scalar_one_or_none()


@router.get("/{project_id}/characters")
async def get_characters(
    project_id: str,
    limit: int = Query(DEFAULT_CHARACTER_PAGE_SIZE, ge=1, le=MAX_CHARACTER_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    project_uuid = _project_uuid(project_id)
    cards = await list_characters(db, project_uuid, limit=limit, offset=offset)
    manifests = await list_project_manifests(
        db,
        project_uuid,
        character_ids=[card.id for card in cards],
    )
    manifest_by_character = {manifest.character_id: manifest for manifest in manifests}
    return {
        "characters": [
            _serialize_card(card, manifest_by_character.get(card.id))
            for card in cards
        ],
        "manifest_read_only": True,
    }


@router.post("/{project_id}/characters/generate")
async def generate_characters(
    project_id: str,
    request: GenerateCharactersRequest,
    db=Depends(get_db),
):
    project_uuid = _project_uuid(project_id)
    novel_result = await db.execute(select(Novel).where(Novel.id == project_uuid))
    novel = novel_result.scalar_one_or_none()
    if novel is None:
        raise HTTPException(status_code=404, detail="Project not found")

    hints = [hint.model_dump() for hint in request.character_hints]
    known_names = {str(item.get("name", "")).strip() for item in hints}
    for name in request.names:
        clean_name = str(name or "").strip()
        if clean_name and clean_name not in known_names:
            hints.append({"name": clean_name})
            known_names.add(clean_name)
    for hint in _outline_character_hints(novel.outline):
        if hint["name"] not in known_names:
            hints.append(hint)
            known_names.add(hint["name"])
    if not hints:
        raise HTTPException(status_code=422, detail="At least one character name or outline character is required")
    if len(hints) > CHARACTER_GENERATION_MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=422,
            detail=f"Character generation batch exceeds {CHARACTER_GENERATION_MAX_BATCH_SIZE} characters",
        )

    from services.character_context import build_planner_manifest_context
    character_manifest = await build_planner_manifest_context(db, project_uuid)
    project_context = {
        "title": novel.title,
        "author": novel.author or "",
        "novel_format": novel.novel_format or NOVEL_FORMAT_LONG_WEBNOVEL,
        "outline": novel.outline or {},
        "existing_character_hints": character_manifest,
    }
    agent = CharacterCardAgent()
    generated = await agent.generate_cards(
        project_context=project_context,
        character_hints=hints,
        user_hints=request.user_hints,
        novel_format=novel.novel_format or NOVEL_FORMAT_LONG_WEBNOVEL,
    )

    existing_cards = await list_characters(db, project_uuid)
    existing_names = {card.name for card in existing_cards}
    created: list[CharacterCard] = []
    skipped: list[str] = []
    for item in generated.get("characters", []):
        name = str(item.get("name") or "").strip()
        if not name or name in existing_names:
            if name:
                skipped.append(name)
            continue
        card = await create_character_card(
            db,
            project_uuid,
            name=name,
            aliases=item.get("aliases") or [],
            card_data=item.get("card_data") or {},
            current_state=item.get("current_state") or {},
            importance=item.get("importance") or CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
            status=item.get("status") or CHARACTER_GENERATION_DEFAULT_STATUS,
        )
        created.append(card)
        existing_names.add(name)

    # Resolve relationships after the complete batch exists, then rebuild all
    # manifests from the same transaction.
    all_cards = await list_characters(db, project_uuid)
    for card in all_cards:
        await sync_card_relationships(db, card)
    manifests = await refresh_project_manifests(db, project_uuid)
    await enqueue_character_manifest_vectors(db, all_cards)
    await db.commit()
    manifest_by_character = {manifest.character_id: manifest for manifest in manifests}
    return {
        "created": [_serialize_card(card, manifest_by_character.get(card.id)) for card in created],
        "skipped": skipped,
    }


@router.get("/{project_id}/characters/{character_id}")
async def get_character_detail(project_id: str, character_id: uuid.UUID, db=Depends(get_db)):
    project_uuid = _project_uuid(project_id)
    card = await get_character(db, project_uuid, character_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character card not found")
    manifest = await _get_manifest(db, card)
    relationships = await list_card_relationships(db, project_uuid, character_id)
    response = _serialize_card(card, manifest)
    response["relationships"] = [
        {
            "id": str(item.id),
            "source_character_id": str(item.source_character_id),
            "target_character_id": str(item.target_character_id),
            "relation_type": item.relation_type,
            "status": item.status,
            "attributes": copy.deepcopy(item.attributes or {}),
            "valid_from_chapter": item.valid_from_chapter,
            "valid_to_chapter": item.valid_to_chapter,
        }
        for item in relationships
    ]
    return response


@router.patch("/{project_id}/characters/{character_id}")
async def patch_character_card(
    project_id: str,
    character_id: uuid.UUID,
    request: UpdateCharacterCardRequest,
    db=Depends(get_db),
):
    project_uuid = _project_uuid(project_id)
    values = request.model_dump(exclude_unset=True)
    try:
        card = await update_character_card(db, project_uuid, character_id, **values)
        await enqueue_character_manifest_vectors(
            db,
            [card],
            chapter_index=request.effective_from_chapter,
        )
        await db.commit()
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    manifest = await _ensure_manifest(db, card)
    return _serialize_card(card, manifest)


@router.get("/{project_id}/characters/{character_id}/states")
async def get_character_states(
    project_id: str,
    character_id: uuid.UUID,
    storyline_id: str = CHARACTER_STORYLINE_MAIN,
    limit: int = Query(DEFAULT_CHARACTER_PAGE_SIZE, ge=1, le=MAX_CHARACTER_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    project_uuid = _project_uuid(project_id)
    card = await get_character(db, project_uuid, character_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character card not found")
    states = await list_character_states(
        db, character_id, storyline_id=storyline_id, limit=limit, offset=offset
    )
    return {"states": [_serialize_state(state) for state in states]}


@router.get("/{project_id}/characters/{character_id}/states/{chapter_index}")
async def get_character_state_at_chapter(
    project_id: str,
    character_id: uuid.UUID,
    chapter_index: int,
    storyline_id: str = CHARACTER_STORYLINE_MAIN,
    db=Depends(get_db),
):
    project_uuid = _project_uuid(project_id)
    if chapter_index < 1:
        raise HTTPException(status_code=422, detail="chapter_index must be positive")
    card = await get_character(db, project_uuid, character_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character card not found")
    state = await get_state_at_chapter(db, character_id, chapter_index, storyline_id)
    return {"state": _serialize_state(state) if state else None}


@router.get("/{project_id}/characters/{character_id}/changes")
async def get_character_changes(
    project_id: str,
    character_id: uuid.UUID,
    limit: int = Query(DEFAULT_CHARACTER_PAGE_SIZE, ge=1, le=MAX_CHARACTER_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    project_uuid = _project_uuid(project_id)
    card = await get_character(db, project_uuid, character_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character card not found")
    changes = await list_character_changes(db, character_id, limit=limit, offset=offset)
    return {"changes": [_serialize_change(change, snapshot) for change, snapshot in changes]}


@router.post("/{project_id}/characters/{character_id}/changes/{change_id}/rollback")
async def rollback_character_change(
    project_id: str,
    character_id: uuid.UUID,
    change_id: uuid.UUID,
    request: RollbackCharacterCardRequest | None = None,
    db=Depends(get_db),
):
    project_uuid = _project_uuid(project_id)
    try:
        card = await rollback_character_card(
            db,
            project_uuid,
            character_id,
            change_id,
            effective_from_chapter=(request.effective_from_chapter if request else None),
        )
        await enqueue_character_manifest_vectors(
            db,
            [card],
            chapter_index=(request.effective_from_chapter if request else None),
        )
        await db.commit()
    except LookupError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    manifest = await _ensure_manifest(db, card)
    return _serialize_card(card, manifest)
