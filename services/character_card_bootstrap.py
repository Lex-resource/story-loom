"""Create complete cards for characters first discovered in a chapter."""

from __future__ import annotations

import copy
import json
from typing import Any

from models.novel import Chapter, Novel
from agents.constants import NOVEL_FORMAT_LONG_WEBNOVEL
from services.character_types import CharacterCardUpdate


def _merge_dicts(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _context_payload(character_card_context: str) -> dict[str, Any]:
    if not character_card_context:
        return {}
    try:
        payload = json.loads(character_card_context)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _candidate_names(payload: dict[str, Any]) -> list[str]:
    names = []
    for item in payload.get("new_character_candidates") or []:
        if not isinstance(item, dict) or item.get("card_exists") is not False:
            continue
        name = str(item.get("name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _character_hints(payload: dict[str, Any], names: list[str]) -> list[dict[str, Any]]:
    by_name = {}
    for item in payload.get("global_character_hints") or []:
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
            by_name[name] = copy.deepcopy(item)
    return [by_name.get(name, {"name": name}) for name in names]


async def generate_initial_character_updates(
    novel: Novel,
    chapter: Chapter,
    character_card_context: str,
) -> tuple[list[CharacterCardUpdate], Any | None]:
    """Generate stable card data only for new, substantive chapter characters."""
    payload = _context_payload(character_card_context)
    names = _candidate_names(payload)
    if not names:
        return [], None

    # Import lazily so the service layer does not create an agent import cycle.
    from agents.character_card_agent import CharacterCardAgent

    agent = CharacterCardAgent()
    agent.project_id = novel.id
    agent.current_chapter = chapter.chapter_index
    generated = await agent.generate_cards(
        project_context={
            "title": novel.title,
            "novel_format": novel.novel_format or "",
            "current_chapter": chapter.chapter_index,
            "chapter_outline": chapter.outline or {},
            "chapter_content": chapter.content or "",
            "character_card_context": payload,
        },
        character_hints=_character_hints(payload, names),
        user_hints=(
            "只为本章首次正式出场且会持续参与剧情的角色生成完整稳定角色卡。"
            "card_data 必须尽可能填写所有适用字段；current_state 只能记录本章正文已经发生的事实。"
            "不要把未来章节大纲当作当前状态。"
        ),
        novel_format=novel.novel_format or NOVEL_FORMAT_LONG_WEBNOVEL,
    )

    updates: list[CharacterCardUpdate] = []
    allowed_names = set(names)
    for item in generated.get("characters", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name not in allowed_names:
            continue
        updates.append(
            CharacterCardUpdate(
                character_name=name,
                card_data_updates=item.get("card_data") or {},
                state_data=item.get("current_state") or {},
                status=item.get("status"),
                card_data_authority="initial",
            )
        )
    return updates, agent


def merge_initial_character_updates(
    initial_updates: list[CharacterCardUpdate],
    extracted_updates: list[CharacterCardUpdate],
) -> list[CharacterCardUpdate]:
    """Combine full first-card data with chapter-local extractor facts."""
    merged: dict[str, CharacterCardUpdate] = {}
    order: list[str] = []

    for update in initial_updates + extracted_updates:
        name = update.character_name
        if name not in merged:
            merged[name] = update.model_copy(deep=True)
            order.append(name)
            continue
        target = merged[name]
        target.card_data_updates = _merge_dicts(
            target.card_data_updates or {},
            update.card_data_updates or {},
        )
        target.state_data = _merge_dicts(
            target.state_data or {},
            update.state_data or {},
        )
        if update.relationships:
            target.relationships = list(target.relationships or []) + copy.deepcopy(update.relationships)
        if update.changed_fields:
            target.changed_fields = list(dict.fromkeys(
                list(target.changed_fields or []) + list(update.changed_fields)
            ))
        if update.status:
            target.status = update.status
    return [merged[name] for name in order]
