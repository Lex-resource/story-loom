"""Deterministic story-event, segment, and stage projections."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.narrative_index import NarrativeIndexEntry
from services.novel_memory_types import STORYLINE_MAIN
from core.source_refs import chapter_source_ref


_NARRATIVE_NAMESPACE = uuid.UUID("5b3f8b7f-6f3c-4cb1-9c62-31b08fbbf2cc")


@dataclass(frozen=True)
class NarrativeProjection:
    entry_type: str
    entry_key: str
    title: str = ""
    content: str = ""
    parent_key: str | None = None
    target_key: str | None = None
    relation: str = "contains"
    chapter_index: int | None = None
    chapter_end: int | None = None
    sequence: int = 0
    source_ref: str = ""
    source_chapter: int | None = None
    authority: str = "published"
    status: str = "accepted"
    confidence: float = 1.0
    data: dict[str, Any] = field(default_factory=dict)


def _hash_projection(projection: NarrativeProjection) -> str:
    payload = {
        "entry_type": projection.entry_type,
        "entry_key": projection.entry_key,
        "title": projection.title,
        "content": projection.content,
        "parent_key": projection.parent_key,
        "target_key": projection.target_key,
        "relation": projection.relation,
        "chapter_index": projection.chapter_index,
        "chapter_end": projection.chapter_end,
        "sequence": projection.sequence,
        "data": projection.data,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def deterministic_narrative_id(
    project_id: uuid.UUID,
    *,
    branch_id: uuid.UUID | None,
    storyline_id: str,
    entry_type: str,
    entry_key: str,
    content_hash: str,
) -> uuid.UUID:
    scope = f"{project_id}:{branch_id or 'mainline'}:{storyline_id}:{entry_type}:{entry_key}:{content_hash}"
    return uuid.uuid5(_NARRATIVE_NAMESPACE, scope)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, "", {}):
        return []
    return [value]


def _item_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("summary", "description", "event", "content", "name", "title"):
            if value.get(key):
                return str(value[key]).strip()
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value or "").strip()


def _stage_key(outline: dict[str, Any]) -> str:
    raw = outline.get("stage") or outline.get("act") or outline.get("plotline") or "mainline"
    return f"stage:{str(raw).strip() or 'mainline'}"


def _event_items(outline: dict[str, Any]) -> list[Any]:
    items = _as_items(outline.get("key_events"))
    if not items:
        items = _as_items(outline.get("required_events"))
    return [item for item in items if _item_text(item)]


def build_narrative_projections(
    *,
    chapter_index: int,
    outline: dict[str, Any] | None,
    handoff: dict[str, Any] | None = None,
    extractor_output: dict[str, Any] | None = None,
) -> list[NarrativeProjection]:
    """Build projections from existing chapter artifacts without an LLM call."""
    outline = _as_dict(outline)
    handoff = _as_dict(handoff)
    extractor_output = _as_dict(extractor_output)
    stage_key = _stage_key(outline)
    source_ref = chapter_source_ref(chapter_index, "narrative_projection")
    projections: list[NarrativeProjection] = []
    stage_content = _item_text(outline.get("summary")) or _item_text(handoff.get("next_hook"))
    projections.append(NarrativeProjection(
        entry_type="stage_summary", entry_key=stage_key, title=stage_key.split(":", 1)[-1],
        content=stage_content, target_key=chapter_source_ref(chapter_index), relation="stage_to_chapter",
        chapter_index=chapter_index, chapter_end=chapter_index, source_ref=source_ref,
        source_chapter=chapter_index, data={"plotline": outline.get("plotline") or "mainline"},
    ))

    raw_segments = _as_items(outline.get("segments") or outline.get("scenes") or outline.get("beats"))
    event_items = _event_items(outline)
    if not raw_segments:
        raw_segments = event_items
    if not raw_segments:
        raw_segments = [stage_content] if stage_content else []

    segment_keys: list[str] = []
    for index, item in enumerate(raw_segments, start=1):
        content = _item_text(item)
        if not content:
            continue
        segment_key = chapter_source_ref(chapter_index, "segment", index)
        segment_keys.append(segment_key)
        projections.append(NarrativeProjection(
            entry_type="story_segment", entry_key=segment_key, title=f"第{chapter_index}章段落 {index}",
            content=content, parent_key=stage_key, relation="segment_to_stage",
            chapter_index=chapter_index, chapter_end=chapter_index, sequence=index,
            source_ref=source_ref, source_chapter=chapter_index, data={"raw": item},
        ))

    if not event_items:
        event_items = raw_segments
    for index, item in enumerate(event_items, start=1):
        content = _item_text(item)
        if not content:
            continue
        event_key = chapter_source_ref(chapter_index, "event", index)
        segment_key = segment_keys[min(index - 1, len(segment_keys) - 1)] if segment_keys else None
        projections.append(NarrativeProjection(
            entry_type="story_event", entry_key=event_key, title=f"第{chapter_index}章事件 {index}",
            content=content, parent_key=chapter_source_ref(chapter_index), target_key=segment_key,
            relation="event_to_chapter", chapter_index=chapter_index, chapter_end=chapter_index,
            sequence=index, source_ref=source_ref, source_chapter=chapter_index,
            data={"raw": item, "stage_key": stage_key},
        ))

    foreshadowing = _as_items(outline.get("related_foreshadowing") or outline.get("foreshadowing"))
    if not foreshadowing:
        foreshadowing = [
            item for item in _as_items(extractor_output.get("patches"))
            if isinstance(item, dict) and str(item.get("category") or "") == "foreshadowing"
        ]
    event_keys = [item.entry_key for item in projections if item.entry_type == "story_event"]
    for index, item in enumerate(foreshadowing, start=1):
        content = _item_text(item)
        if not content or not event_keys:
            continue
        memory_key = item.get("name") if isinstance(item, dict) else None
        link_key = f"chapter:{chapter_index}:foreshadowing:{memory_key or index}"
        projections.append(NarrativeProjection(
            entry_type="foreshadowing_link", entry_key=link_key, title="伏笔关联", content=content,
            parent_key=str(memory_key or content), target_key=event_keys[min(index - 1, len(event_keys) - 1)],
            relation="foreshadowing_to_event", chapter_index=chapter_index, chapter_end=chapter_index,
            sequence=index, source_ref=source_ref, source_chapter=chapter_index, data={"raw": item},
        ))
    return projections


async def persist_narrative_projections(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    projections: Iterable[NarrativeProjection],
    branch_id: uuid.UUID | None = None,
    storyline_id: str = STORYLINE_MAIN,
) -> list[NarrativeIndexEntry]:
    persisted: list[NarrativeIndexEntry] = []
    for projection in projections:
        content_hash = _hash_projection(projection)
        row_id = deterministic_narrative_id(
            project_id, branch_id=branch_id, storyline_id=storyline_id,
            entry_type=projection.entry_type, entry_key=projection.entry_key,
            content_hash=content_hash,
        )
        values = {
            "id": row_id, "project_id": project_id, "branch_id": branch_id,
            "storyline_id": storyline_id, "source_ref": projection.source_ref,
            "source_chapter": projection.source_chapter,
            "confidence": max(0.0, min(1.0, float(projection.confidence))), "version": 1,
            "authority": projection.authority, "entry_type": projection.entry_type,
            "entry_key": projection.entry_key, "parent_key": projection.parent_key,
            "target_key": projection.target_key, "relation": projection.relation,
            "chapter_index": projection.chapter_index, "chapter_end": projection.chapter_end,
            "sequence": projection.sequence, "content_hash": content_hash,
            "title": projection.title, "content": projection.content, "data": projection.data,
            "status": projection.status, "is_active": True,
        }
        await db.execute(pg_insert(NarrativeIndexEntry).values(**values).on_conflict_do_nothing())
        row = await db.scalar(select(NarrativeIndexEntry).where(NarrativeIndexEntry.id == row_id))
        if row is not None:
            persisted.append(row)
    return persisted


async def sync_narrative_index(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    chapter_index: int,
    outline: dict[str, Any] | None,
    handoff: dict[str, Any] | None = None,
    extractor_output: dict[str, Any] | None = None,
    branch_id: uuid.UUID | None = None,
    storyline_id: str = STORYLINE_MAIN,
) -> list[NarrativeIndexEntry]:
    return await persist_narrative_projections(
        db, project_id=project_id,
        projections=build_narrative_projections(
            chapter_index=chapter_index, outline=outline, handoff=handoff,
            extractor_output=extractor_output,
        ), branch_id=branch_id, storyline_id=storyline_id,
    )


NARRATIVE_AGENT_TYPES: dict[str, set[str]] = {
    "planner": {"stage_summary", "story_event", "foreshadowing_link"},
    "writer": {"story_event", "foreshadowing_link"},
    "editor": {"story_event", "foreshadowing_link"},
    "validator": {"story_event", "foreshadowing_link"},
    "extractor": {"story_event", "foreshadowing_link"},
}


def format_narrative_context(
    entries: Iterable[NarrativeIndexEntry],
    max_chars: int = 1200,
    *,
    agent_type: str = "writer",
) -> str:
    allowed_types = NARRATIVE_AGENT_TYPES.get(agent_type, NARRATIVE_AGENT_TYPES["writer"])
    lines: list[str] = []
    seen_content: set[str] = set()
    for entry in entries:
        content = str(entry.content or "").strip()
        if (
            entry.status != "accepted"
            or not entry.is_active
            or entry.entry_type not in allowed_types
            or not content
            or content in seen_content
        ):
            continue
        seen_content.add(content)
        relation = f" [{entry.relation}]" if entry.relation else ""
        line = f"- {entry.entry_type}:{entry.entry_key}{relation}: {content}"
        if len("\n".join(lines)) + len(line) + 1 > max_chars:
            break
        lines.append(line)
    return "\n".join(lines)
