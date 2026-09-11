"""Pure settings-index slicing for vector search."""
import hashlib
import json

from services.vector_constants import (
    VECTOR_SETTING_CHARACTER_ID_TEMPLATE,
    VECTOR_SOURCE_SETTING,
    VECTOR_TYPE_CHARACTER_STATE,
)
from services.living_docs_parsers import parse_bullet_points, parse_character_state
from services.knowledge_constants import FORESHADOWING_STATUS_ACTIVE
from services.knowledge_markdown import knowledge_from_markdown


def settings_content_hash(
    character_state: str,
    world_state: str,
    foreshadowing: str,
    plot_threads: str,
) -> str:
    payload = "\n---\n".join(
        [
            "setting-index-v2",
            character_state or "",
            world_state or "",
            foreshadowing or "",
            plot_threads or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def character_setting_vector_id(name: str) -> str:
    return VECTOR_SETTING_CHARACTER_ID_TEMPLATE.format(name=name)


def build_character_manifest_vector_item(name: str, manifest_data: dict) -> dict:
    return {
        "id": character_setting_vector_id(name),
        "description": json.dumps(manifest_data, ensure_ascii=False, sort_keys=True),
        "source": VECTOR_SOURCE_SETTING,
        "type": VECTOR_TYPE_CHARACTER_STATE,
        "name": name,
    }


def build_setting_entries(
    character_state: str,
    world_state: str,
    foreshadowing: str,
    plot_threads: str,
) -> list[tuple[str, str, dict]]:
    """Build stable vector rows for living-doc settings slices."""
    entries: list[tuple[str, str, dict]] = []

    for name, block in parse_character_state(character_state):
        entries.append(
            (
                character_setting_vector_id(name),
                block,
                {"source": VECTOR_SOURCE_SETTING, "type": VECTOR_TYPE_CHARACTER_STATE, "name": name},
            )
        )

    for idx, rule in enumerate(parse_bullet_points(world_state)):
        entries.append(
            (
                f"setting_world_{idx}",
                rule,
                {"source": VECTOR_SOURCE_SETTING, "type": "world_state", "index": idx},
            )
        )

    for idx, item, metadata in _foreshadowing_entries(foreshadowing):
        entries.append(
            (
                f"setting_foreshadowing_{idx}",
                item,
                {
                    "source": VECTOR_SOURCE_SETTING,
                    "type": "foreshadowing",
                    "index": idx,
                    **metadata,
                },
            )
        )

    for idx, item in enumerate(parse_bullet_points(plot_threads)):
        data = _json_dict(item)
        chapter = _first_int(data, "chapter_updated", "chapter_created", "chapter", "last_chapter")
        status = str(data.get("status", "active")) if data else "active"
        if status not in ("active", "ongoing", "open"):
            continue
        entries.append(
            (
                f"setting_plot_{idx}",
                item,
                {
                    "source": VECTOR_SOURCE_SETTING,
                    "type": "plot_threads",
                    "index": idx,
                    "status": status,
                    "chapter": chapter or 0,
                    "name": str(data.get("name", "")) if data else "",
                },
            )
        )

    return entries


def _foreshadowing_entries(content: str) -> list[tuple[int, str, dict]]:
    markdown_items = knowledge_from_markdown("foreshadowing", content)
    if markdown_items:
        entries = []
        for idx, item in enumerate(markdown_items):
            if getattr(item, "status", FORESHADOWING_STATUS_ACTIVE) != FORESHADOWING_STATUS_ACTIVE:
                continue
            doc = json.dumps(item.model_dump(), ensure_ascii=False)
            entries.append((idx, doc, _foreshadowing_metadata(item.model_dump())))
        return entries

    entries = []
    for idx, line in enumerate(content.strip().split("\n")):
        line = line.strip()
        if not line:
            continue
        data = _json_dict(line)
        if data:
            if data.get("status", FORESHADOWING_STATUS_ACTIVE) != FORESHADOWING_STATUS_ACTIVE:
                continue
            item = json.dumps(data, ensure_ascii=False)
            metadata = _foreshadowing_metadata(data)
        else:
            item = line
            metadata = {
                "status": FORESHADOWING_STATUS_ACTIVE,
                "chapter": 0,
                "importance": "",
                "name": "",
            }
        entries.append((idx, item, metadata))
    return entries


def _foreshadowing_metadata(data: dict) -> dict:
    return {
        "status": str(data.get("status", FORESHADOWING_STATUS_ACTIVE)),
        "chapter": _first_int(data, "chapter", "chapter_created") or 0,
        "importance": str(data.get("importance", "")),
        "name": str(data.get("name", "")),
    }


def _json_dict(text: str) -> dict:
    try:
        data = json.loads(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _first_int(data: dict, *keys: str) -> int | None:
    for key in keys:
        value = data.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None
