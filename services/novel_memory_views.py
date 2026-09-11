"""Read-only views for the frontend backed by accepted layered memory."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel_memory import NovelMemoryAtom
from services.novel_memory_types import ATOM_STATUS_ACCEPTED, STORYLINE_MAIN

DEFAULT_KNOWLEDGE_VIEW_LIMIT = 1000
MAX_KNOWLEDGE_VIEW_LIMIT = 5000


def _name(atom) -> str:
    return str(atom.memory_key or atom.statement[:80]).split(":", 1)[-1]


def _chapter(atom) -> int | None:
    """Use the persisted source chapter, with legacy payload fallback."""
    if atom.source_chapter is not None:
        return atom.source_chapter
    data = atom.data if isinstance(atom.data, dict) else {}
    value = data.get("chapter") or data.get("source_chapter")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timeline_sort_key(item: dict) -> tuple[bool, int]:
    """Sort records with an unknown legacy chapter after numbered records."""
    chapter = item["chapter"]
    return chapter is None, chapter if chapter is not None else 0


def _bounded_view_limit(limit: int) -> int:
    return min(max(int(limit), 1), MAX_KNOWLEDGE_VIEW_LIMIT)


async def _atoms(
    db: AsyncSession,
    project_id,
    atom_type: str,
    *,
    limit: int = DEFAULT_KNOWLEDGE_VIEW_LIMIT,
):
    bounded_limit = _bounded_view_limit(limit)
    result = await db.scalars(
        select(NovelMemoryAtom)
        .where(
            NovelMemoryAtom.project_id == project_id,
            NovelMemoryAtom.branch_id.is_(None),
            NovelMemoryAtom.storyline_id == STORYLINE_MAIN,
            NovelMemoryAtom.atom_type == atom_type,
            NovelMemoryAtom.status == ATOM_STATUS_ACCEPTED,
        )
        .order_by(
            nulls_last(NovelMemoryAtom.source_chapter.desc()),
            NovelMemoryAtom.version.desc(),
            NovelMemoryAtom.id.asc(),
        )
        .limit(bounded_limit)
    )
    return list(result.all())


def _latest_atoms(atoms: list) -> list:
    """Collapse historical versions for snapshot-style graph views."""
    latest = {}
    for atom in atoms:
        key = str(atom.memory_key or atom.statement[:80])
        previous = latest.get(key)
        if previous is None or (atom.version or 0) > (previous.version or 0):
            latest[key] = atom
    return list(latest.values())


async def build_world_rules_view(
    db: AsyncSession,
    project_id,
    *,
    limit: int = DEFAULT_KNOWLEDGE_VIEW_LIMIT,
) -> dict:
    atoms = _latest_atoms(await _atoms(db, project_id, "world_rule", limit=limit))
    categories = {
        "rule": "世界法则",
        "location": "地理空间",
        "faction": "势力组织",
        "restriction": "限制禁忌",
        "confirmed": "已验真理",
    }
    nodes = [{"id": "root", "label": "世界设定", "group": "root", "title": "世界设定根节点"}]
    edges = []
    details = {}
    for key, label in categories.items():
        nodes.append({"id": f"cat_{key}", "label": label, "group": "category", "title": label})
        edges.append({"from": "root", "to": f"cat_{key}", "label": "类别"})
    for atom in atoms:
        data = atom.data if isinstance(atom.data, dict) else {}
        category = str(data.get("rule_type") or data.get("type") or "rule").lower()
        category = category if category in categories else "rule"
        name = _name(atom)
        nodes.append({"id": name, "label": name, "group": category, "title": name})
        edges.append({"from": f"cat_{category}", "to": name, "label": "包含"})
        details[name] = {
            "tag": category,
            "tag_display": categories[category],
            "content": atom.statement,
            "chapter": _chapter(atom),
        }
    return {"nodes": nodes, "edges": edges, "details": details}


async def build_foreshadowing_view(
    db: AsyncSession,
    project_id,
    *,
    limit: int = DEFAULT_KNOWLEDGE_VIEW_LIMIT,
) -> dict:
    atoms = await _atoms(db, project_id, "foreshadowing", limit=limit)
    grouped = defaultdict(list)
    for atom in atoms:
        data = atom.data if isinstance(atom.data, dict) else {}
        operation = data.get("operation", "upsert")
        event_type = "resolve" if operation == "resolve" else "cancel" if operation == "cancel" else "plant"
        grouped[_name(atom)].append({
            "chapter": _chapter(atom),
            "type": event_type,
            "desc": atom.statement,
        })
    return {
        "chains": [
            {"id": name, "title": name, "events": sorted(events, key=_timeline_sort_key)}
            for name, events in grouped.items()
        ]
    }


async def build_plot_tracks_view(
    db: AsyncSession,
    project_id,
    *,
    limit: int = DEFAULT_KNOWLEDGE_VIEW_LIMIT,
) -> dict:
    atoms = await _atoms(db, project_id, "plot_thread", limit=limit)
    grouped = defaultdict(list)
    for atom in atoms:
        name = _name(atom)
        grouped[name].append({
            "chapter": _chapter(atom),
            "thread": name,
            "progress": atom.statement,
        })
    events = [event for items in grouped.values() for event in items]
    return {"threads": list(grouped), "events": sorted(events, key=_timeline_sort_key)}
