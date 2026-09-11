"""Deterministic database projection for Planner and character browsing."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.characters import (
    CharacterArc,
    CharacterCard,
    CharacterManifest,
    CharacterRelationship,
)
from services.character_constants import (
    CHARACTER_CONTEXT_MAX_MANIFESTS,
    CHARACTER_GENERATION_DEFAULT_IMPORTANCE,
    CHARACTER_GENERATION_DEFAULT_STATUS,
    CHARACTER_MANIFEST_SUMMARY_MAX_CHARS,
    CHARACTER_RELATIONSHIP_DEFAULT_TYPE,
)
from services.character_schemas import normalize_current_state
from services.knowledge_types import CharacterKnowledge


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _summary_text(value: Any, limit: int = CHARACTER_MANIFEST_SUMMARY_MAX_CHARS) -> str:
    if isinstance(value, list):
        text = "、".join(str(item) for item in value if item not in (None, ""))
    elif isinstance(value, dict):
        text = "；".join(f"{key}: {item}" for key, item in value.items() if item not in (None, ""))
    else:
        text = str(value or "")
    return text.strip()[:limit]


def _first_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def build_manifest_data(
    card: CharacterCard,
    relationships: Iterable[CharacterRelationship] = (),
    arcs: Iterable[CharacterArc] = (),
    character_names: dict[Any, str] | None = None,
) -> dict[str, Any]:
    card_data = card.card_data or {}
    identity = card_data.get("identity") or {}
    personality = card_data.get("personality") or {}
    growth_route = card_data.get("growth_route") or {}
    current_state = normalize_current_state(card.current_state or {})

    relationship_summary = []
    for relationship in relationships:
        attrs = relationship.attributes or {}
        relationship_summary.append({
            "target_character_id": str(relationship.target_character_id),
            "target_name": (character_names or {}).get(relationship.target_character_id, ""),
            "relation_type": relationship.relation_type,
            "status": relationship.status,
            "summary": _summary_text(
                attrs.get("source_perspective")
                or attrs.get("summary")
                or attrs.get("description")
                or ""
            ),
        })

    arc_summary = [
        {
            "id": str(arc.id),
            "name": arc.name,
            "storyline_id": arc.storyline_id,
            "arc_type": arc.arc_type,
            "status": arc.status,
            "anchor_chapter": arc.anchor_chapter,
            "target_chapter": arc.target_chapter,
        }
        for arc in arcs
    ]

    return {
        "character_id": str(card.id),
        "name": card.name,
        "aliases": card.aliases or [],
        "importance": card.importance,
        "status": card.status,
        "role_summary": _summary_text({
            "身份": _first_value(identity, "occupation", "role", "身份", "角色"),
            "立场": _first_value(identity, "faction", "camp", "当前立场", "立场"),
            "社会身份": _first_value(identity, "social_status", "社会身份"),
        }),
        "personality_summary": _summary_text({
            "特征": _first_value(personality, "traits", "特征", "性格"),
            "优点": _first_value(personality, "strengths", "优点"),
            "缺点": _first_value(personality, "weaknesses", "缺点"),
            "底线": _first_value(personality, "moral_boundaries", "底线"),
        }),
        "current_stage": _first_value(growth_route, "current_stage", "当前阶段", "阶段"),
        "current_goal": _first_value(current_state, "goal", "当前目标", "目标") or _first_value(growth_route, "current_goal", "当前目标", "目标"),
        "current_location": _first_value(current_state, "location", "current_location", "位置", "当前地点"),
        "current_emotion": _first_value(current_state, "emotion", "当前情绪", "心情"),
        "last_appearance": card.last_appearance,
        "open_threads": _as_list(
            current_state.get("open_threads")
            or growth_route.get("open_threads")
        ),
        "relationships": relationship_summary,
        "arcs": arc_summary,
        "constraints": _as_list(card_data.get("constraints")),
    }


def manifest_to_legacy_knowledge(data: dict[str, Any]) -> CharacterKnowledge:
    """Expose a manifest as the old read-only knowledge DTO."""
    relationships = []
    for relationship in data.get("relationships") or []:
        if not isinstance(relationship, dict):
            continue
        relationships.append({
            "to": relationship.get("target_name") or relationship.get("target_character_id", ""),
            "label": relationship.get("relation_type", CHARACTER_RELATIONSHIP_DEFAULT_TYPE),
            "description": relationship.get("summary", ""),
        })
    attributes = {
        "role_summary": data.get("role_summary", ""),
        "personality_summary": data.get("personality_summary", ""),
        "current_stage": data.get("current_stage", ""),
        "current_goal": data.get("current_goal", ""),
        "current_location": data.get("current_location", ""),
        "current_emotion": data.get("current_emotion", ""),
        "open_threads": data.get("open_threads", []),
        "arcs": data.get("arcs", []),
        "constraints": data.get("constraints", []),
        "relationships": relationships,
    }
    return CharacterKnowledge(
        name=str(data.get("name") or ""),
        aliases=list(data.get("aliases") or []),
        importance=str(data.get("importance") or CHARACTER_GENERATION_DEFAULT_IMPORTANCE),
        status=str(data.get("status") or CHARACTER_GENERATION_DEFAULT_STATUS),
        body=str(data.get("role_summary") or ""),
        attributes={key: value for key, value in attributes.items() if value not in (None, "", [])},
        chapter_updated=data.get("last_appearance"),
    )


def manifest_to_markdown(data: dict[str, Any]) -> str:
    """Render the persisted manifest without an LLM or editable source file."""
    lines = [f"## {data.get('name', '')}"]
    for label, key in (
        ("身份摘要", "role_summary"),
        ("性格摘要", "personality_summary"),
        ("成长阶段", "current_stage"),
        ("当前目标", "current_goal"),
        ("当前位置", "current_location"),
        ("当前情绪", "current_emotion"),
    ):
        value = data.get(key)
        if value:
            lines.append(f"- **{label}**: {value}")
    open_threads = data.get("open_threads") or []
    if open_threads:
        lines.append("### 未完成事项")
        lines.extend(f"- {item}" for item in open_threads)
    arcs = data.get("arcs") or []
    if arcs:
        lines.append("### 成长路线")
        for arc in arcs:
            if not isinstance(arc, dict):
                continue
            route_name = arc.get("name") or ""
            route_status = arc.get("status") or ""
            route_target = arc.get("target_chapter")
            suffix = f"，目标章节：{route_target}" if route_target else ""
            status = f"（{route_status}）" if route_status else ""
            lines.append(f"- {route_name}{status}{suffix}")
    relationships = data.get("relationships") or []
    if relationships:
        lines.append("### 关系")
        for relationship in relationships:
            target = relationship.get("target_name") or relationship.get("target_character_id", "")
            summary = relationship.get("summary") or ""
            suffix = f"：{summary}" if summary else ""
            relation_type = relationship.get("relation_type", CHARACTER_RELATIONSHIP_DEFAULT_TYPE)
            lines.append(f"- {target}（{relation_type}）{suffix}")
    constraints = data.get("constraints") or []
    if constraints:
        lines.append("### 写作约束")
        lines.extend(f"- {item}" for item in constraints)
    return "\n".join(lines)


async def list_project_manifests(
    db: AsyncSession,
    project_id,
    *,
    limit: int = CHARACTER_CONTEXT_MAX_MANIFESTS,
    character_ids=None,
) -> list[CharacterManifest]:
    statement = select(CharacterManifest).where(CharacterManifest.project_id == project_id)
    if character_ids is not None:
        statement = statement.where(CharacterManifest.character_id.in_(character_ids))
        limit = len(character_ids)
    result = await db.execute(
        statement.order_by(CharacterManifest.updated_at.desc(), CharacterManifest.id.asc()).limit(limit)
    )
    return list(result.scalars().all())


async def read_project_manifest_knowledge(db: AsyncSession, project_id) -> list[CharacterKnowledge]:
    manifests = await list_project_manifests(db, project_id)
    return [manifest_to_legacy_knowledge(manifest.data or {}) for manifest in manifests]


async def read_project_manifest_markdown(db: AsyncSession, project_id) -> str:
    manifests = await list_project_manifests(db, project_id)
    return "\n\n".join(manifest_to_markdown(manifest.data or {}) for manifest in manifests)


async def refresh_manifest(db: AsyncSession, card: CharacterCard) -> CharacterManifest:
    relationships_result = await db.execute(
        select(CharacterRelationship)
        .where(CharacterRelationship.source_character_id == card.id)
        .order_by(CharacterRelationship.id)
    )
    arcs_result = await db.execute(
        select(CharacterArc)
        .where(CharacterArc.character_id == card.id)
        .order_by(CharacterArc.created_at, CharacterArc.id)
    )
    relationships = list(relationships_result.scalars().all())
    target_ids = {relationship.target_character_id for relationship in relationships}
    target_names: dict[Any, str] = {}
    if target_ids:
        target_result = await db.execute(
            select(CharacterCard.id, CharacterCard.name).where(CharacterCard.id.in_(target_ids))
        )
        target_names = {character_id: name for character_id, name in target_result.all()}
    data = build_manifest_data(
        card,
        relationships,
        arcs_result.scalars().all(),
        character_names=target_names,
    )
    checksum = json_checksum(data)
    result = await db.execute(
        select(CharacterManifest).where(CharacterManifest.character_id == card.id)
    )
    manifest = result.scalar_one_or_none()
    if manifest is None:
        manifest = CharacterManifest(
            project_id=card.project_id,
            character_id=card.id,
            data=data,
            checksum=checksum,
            is_read_only=True,
        )
        db.add(manifest)
    else:
        manifest.data = data
        manifest.checksum = checksum
        manifest.is_read_only = True
    await db.flush()
    return manifest


async def refresh_project_manifests(db: AsyncSession, project_id) -> list[CharacterManifest]:
    result = await db.execute(
        select(CharacterCard).where(CharacterCard.project_id == project_id).order_by(CharacterCard.name)
    )
    manifests = []
    for card in result.scalars().all():
        manifests.append(await refresh_manifest(db, card))
    return manifests
