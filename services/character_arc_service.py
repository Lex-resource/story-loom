"""Synchronize card-defined growth routes into the graph-facing arc table."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.characters import CharacterArc, CharacterCard
from services.character_constants import (
    CHARACTER_ARC_DEFAULT_STATUS,
    CHARACTER_ARC_MAIN,
    CHARACTER_ARC_MAIN_NAME,
    CHARACTER_ARC_NAME_KEYS,
    CHARACTER_ARC_SIDE,
    CHARACTER_ARC_SIDE_NAME_PREFIX,
    CHARACTER_ARC_SOURCE_CARD,
    CHARACTER_STORYLINE_MAIN,
)


def _positive_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _arc_name(item: dict[str, Any], arc_type: str, index: int) -> str:
    for key in CHARACTER_ARC_NAME_KEYS:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    if arc_type == CHARACTER_ARC_MAIN:
        return CHARACTER_ARC_MAIN_NAME
    return f"{CHARACTER_ARC_SIDE_NAME_PREFIX} {index + 1}"


def _normalise_arc(
    raw: Any,
    *,
    arc_type: str,
    index: int,
) -> dict[str, Any] | None:
    if raw in (None, ""):
        return None
    item = copy.deepcopy(raw) if isinstance(raw, dict) else {"summary": str(raw)}
    name = _arc_name(item, arc_type, index)
    storyline_id = str(item.get("storyline_id") or CHARACTER_STORYLINE_MAIN).strip()
    status = str(item.get("status") or CHARACTER_ARC_DEFAULT_STATUS).strip()
    data = copy.deepcopy(item)
    data["source"] = CHARACTER_ARC_SOURCE_CARD
    return {
        "storyline_id": storyline_id or CHARACTER_STORYLINE_MAIN,
        "arc_type": arc_type,
        "name": name,
        "anchor_chapter": _positive_int(item.get("anchor_chapter")),
        "target_chapter": _positive_int(item.get("target_chapter")),
        "status": status or CHARACTER_ARC_DEFAULT_STATUS,
        "data": data,
    }


def _desired_arcs(card: CharacterCard) -> list[dict[str, Any]]:
    card_data = card.card_data or {}
    desired: list[dict[str, Any]] = []
    main_arc = card_data.get("main_arc")
    if main_arc:
        normalised = _normalise_arc(main_arc, arc_type=CHARACTER_ARC_MAIN, index=0)
        if normalised:
            desired.append(normalised)

    side_arcs = card_data.get("side_arcs") or []
    if not isinstance(side_arcs, list):
        side_arcs = [side_arcs]
    for index, side_arc in enumerate(side_arcs):
        normalised = _normalise_arc(side_arc, arc_type=CHARACTER_ARC_SIDE, index=index)
        if normalised:
            desired.append(normalised)
    return desired


async def sync_card_arcs(
    db: AsyncSession,
    card: CharacterCard,
) -> list[CharacterArc]:
    """Reconcile card routes while preserving future non-mainline branches."""
    result = await db.execute(
        select(CharacterArc).where(CharacterArc.character_id == card.id)
    )
    existing = list(result.scalars().all())
    desired = _desired_arcs(card)
    desired_by_key = {
        (item["storyline_id"], item["arc_type"], item["name"]): item
        for item in desired
    }
    synced: list[CharacterArc] = []

    for arc in existing:
        is_card_managed = (
            (arc.data or {}).get("source") == CHARACTER_ARC_SOURCE_CARD
            or arc.storyline_id == CHARACTER_STORYLINE_MAIN
        )
        if not is_card_managed:
            continue
        key = (arc.storyline_id, arc.arc_type, arc.name)
        item = desired_by_key.get(key)
        if item is None:
            await db.delete(arc)
            continue
        arc.anchor_chapter = item["anchor_chapter"]
        arc.target_chapter = item["target_chapter"]
        arc.status = item["status"]
        arc.data = item["data"]
        synced.append(arc)

    existing_keys = {
        (arc.storyline_id, arc.arc_type, arc.name)
        for arc in existing
        if (arc.data or {}).get("source") == CHARACTER_ARC_SOURCE_CARD
        or arc.storyline_id == CHARACTER_STORYLINE_MAIN
    }
    for key, item in desired_by_key.items():
        if key in existing_keys:
            continue
        arc = CharacterArc(
            project_id=card.project_id,
            character_id=card.id,
            storyline_id=item["storyline_id"],
            arc_type=item["arc_type"],
            name=item["name"],
            anchor_chapter=item["anchor_chapter"],
            target_chapter=item["target_chapter"],
            status=item["status"],
            data=item["data"],
        )
        db.add(arc)
        synced.append(arc)

    await db.flush()
    return synced
