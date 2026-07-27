import json
from collections.abc import Awaitable, Callable
from typing import Optional

from services.vector_constants import (
    VECTOR_ACTIVE_CONTEXT_RECENT_CHAPTER_WINDOW,
    VECTOR_CHARACTER_QUERY_N_RESULTS,
    VECTOR_CHAPTER_EXTRACTS_N_RESULTS,
    VECTOR_COLLECTION_PREFIX,
    VECTOR_DUE_FORESHADOWING_LIMIT,
    VECTOR_FALLBACK_LIST_SIZE,
    VECTOR_FORESHADOWING_N_RESULTS,
    VECTOR_PLOT_THREADS_N_RESULTS,
    VECTOR_SOURCE_CHAPTER_EXTRACT,
    VECTOR_SOURCE_SETTING,
    VECTOR_WORLD_RULES_N_RESULTS,
)
from services.knowledge_constants import (
    DEBT_TYPE_FORESHADOWING,
    DEBT_TYPE_LABELS,
    FORESHADOWING_STATUS_ACTIVE,
)
from services.knowledge_markdown import knowledge_from_markdown
from services.knowledge_types import ForeshadowingKnowledge
from services.living_docs_parsers import parse_bullet_points, parse_character_state
from services.vector_context_formatting import format_chapter_extracts

QueryCollection = Callable[..., Awaitable[dict]]


async def retrieve_chapter_extracts(
    project_id: str,
    query_text: str,
    query_collection: QueryCollection,
) -> str:
    collection_name = f"{VECTOR_COLLECTION_PREFIX}{project_id}"
    documents: list[str] = []
    metadatas: list[dict] = []

    try:
        res = await query_collection(
            collection_name=collection_name,
            query_texts=[query_text],
            n_results=VECTOR_CHAPTER_EXTRACTS_N_RESULTS,
            where={"source": VECTOR_SOURCE_CHAPTER_EXTRACT},
        )
        documents.extend(res.get("documents", [[]])[0] or [])
        metadatas.extend(res.get("metadatas", [[]])[0] or [])
    except Exception as e:
        print(f"Error querying chapter_extract vectors: {e}")

    # Legacy rows written before source=chapter_extract.
    if len(documents) < 3:
        try:
            legacy = await query_collection(
                collection_name=collection_name,
                query_texts=[query_text],
                n_results=VECTOR_CHAPTER_EXTRACTS_N_RESULTS,
                where={"type": {"$in": ["character", "event", "setting"]}},
            )
            for doc, meta in zip(
                legacy.get("documents", [[]])[0] or [],
                legacy.get("metadatas", [[]])[0] or [],
            ):
                if meta and meta.get("source") == VECTOR_SOURCE_SETTING:
                    continue
                documents.append(doc)
                metadatas.append(meta or {})
        except Exception as e:
            print(f"Error querying legacy chapter vectors: {e}")

    return format_chapter_extracts(documents, metadatas)


async def retrieve_setting_context(
    project_id: str,
    query_text: str,
    character_state_txt: str,
    world_state_txt: str,
    foreshadowing_txt: str,
    plot_threads_txt: str,
    query_collection: QueryCollection,
    characters_involved_hint: Optional[list[str]] = None,
    protagonist_name: Optional[str] = None,
    current_chapter: Optional[int] = None,
    foreshadowing_items: Optional[list[ForeshadowingKnowledge]] = None,
) -> dict:
    chars = parse_character_state(character_state_txt)
    char_map = {name: block for name, block in chars}
    all_names = list(char_map.keys())

    matched_names = []
    if characters_involved_hint:
        for name in characters_involved_hint:
            if name in char_map and name not in matched_names:
                matched_names.append(name)

    for name in all_names:
        if name in query_text and name not in matched_names:
            matched_names.append(name)

    protagonist_name = _resolve_protagonist_name(
        char_map, matched_names, protagonist_name
    )
    if protagonist_name and protagonist_name not in matched_names:
        matched_names.append(protagonist_name)

    try:
        char_res = await query_collection(
            collection_name=f"{VECTOR_COLLECTION_PREFIX}{project_id}",
            query_texts=[query_text],
            n_results=VECTOR_CHARACTER_QUERY_N_RESULTS,
            where={"$and": [{"source": VECTOR_SOURCE_SETTING}, {"type": "character_state"}]},
        )
        for meta in char_res.get("metadatas", [[]])[0]:
            if meta and meta.get("name"):
                name = meta["name"]
                if name in char_map and name not in matched_names:
                    matched_names.append(name)
    except Exception as e:
        print(f"Error querying characters from vector store: {e}")

    retrieved_characters = "\n\n".join([char_map[name] for name in matched_names])
    retrieved_world = await _retrieve_or_fallback(
        project_id,
        query_text,
        query_collection,
        item_type="world_state",
        fallback_text=world_state_txt,
        fallback_limit=VECTOR_FALLBACK_LIST_SIZE,
        query_limit=VECTOR_WORLD_RULES_N_RESULTS,
        error_label="world rules",
        current_chapter=current_chapter,
    )
    retrieved_foreshadowing = await _retrieve_or_fallback(
        project_id,
        query_text,
        query_collection,
        item_type="foreshadowing",
        fallback_text=foreshadowing_txt,
        fallback_limit=VECTOR_FALLBACK_LIST_SIZE,
        query_limit=VECTOR_FORESHADOWING_N_RESULTS,
        error_label="foreshadowing",
        current_chapter=current_chapter,
    )
    retrieved_foreshadowing = _append_due_foreshadowing_context(
        retrieved_foreshadowing,
        foreshadowing_txt,
        current_chapter=current_chapter,
        limit=VECTOR_DUE_FORESHADOWING_LIMIT,
        structured_items=foreshadowing_items,
    )
    retrieved_plot = await _retrieve_or_fallback(
        project_id,
        query_text,
        query_collection,
        item_type="plot_threads",
        fallback_text=plot_threads_txt,
        fallback_limit=VECTOR_PLOT_THREADS_N_RESULTS,
        query_limit=VECTOR_PLOT_THREADS_N_RESULTS,
        error_label="plot threads",
        current_chapter=current_chapter,
    )

    chapter_extracts = await retrieve_chapter_extracts(
        project_id, query_text, query_collection
    )
    if chapter_extracts:
        retrieved_world = (
            f"{retrieved_world}\n\n【相关历史章节片段】\n{chapter_extracts}"
        ).strip()

    return {
        "character_state": retrieved_characters,
        "world_state": retrieved_world,
        "foreshadowing": retrieved_foreshadowing,
        "plot_threads": retrieved_plot,
        "chapter_extracts": chapter_extracts,
    }


async def search_knowledge_items(
    project_id: str,
    query: str,
    query_collection: QueryCollection,
    item_type: Optional[str] = None,
    n: int = 5,
) -> dict:
    where = {"type": item_type} if item_type else None
    results = await query_collection(
        collection_name=f"{VECTOR_COLLECTION_PREFIX}{project_id}",
        query_texts=[query],
        n_results=n,
        where=where,
    )
    return {
        "documents": results.get("documents", [[]])[0] if results.get("documents") else [],
        "metadatas": results.get("metadatas", [[]])[0] if results.get("metadatas") else [],
        "distances": results.get("distances", [[]])[0] if results.get("distances") else [],
    }


def _resolve_protagonist_name(
    char_map: dict[str, str],
    matched_names: list[str],
    protagonist_name: Optional[str],
) -> Optional[str]:
    if protagonist_name and protagonist_name in char_map:
        return protagonist_name
    if protagonist_name:
        return None
    for name, block in char_map.items():
        if name in matched_names:
            continue
        if "主角" in block or "protagonist" in block.lower():
            return name
    return None


async def _retrieve_or_fallback(
    project_id: str,
    query_text: str,
    query_collection: QueryCollection,
    *,
    item_type: str,
    fallback_text: str,
    fallback_limit: int,
    query_limit: int,
    error_label: str,
    current_chapter: Optional[int] = None,
) -> str:
    retrieved = ""
    try:
        result = await query_collection(
            collection_name=f"{VECTOR_COLLECTION_PREFIX}{project_id}",
            query_texts=[query_text],
            n_results=query_limit,
            where=_setting_where(item_type),
        )
        retrieved = _join_retrieved_documents(
            result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0],
            item_type=item_type,
            current_chapter=current_chapter,
            limit=query_limit,
        )
    except Exception as e:
        print(f"Error querying {error_label}: {e}")

    if retrieved.strip():
        return retrieved
    return "\n".join(
        _fallback_items(
            fallback_text,
            item_type=item_type,
            limit=fallback_limit,
            current_chapter=current_chapter,
        )
    )


def _setting_where(item_type: str) -> dict:
    clauses = [{"source": VECTOR_SOURCE_SETTING}, {"type": item_type}]
    if item_type == "foreshadowing":
        clauses.append({"status": FORESHADOWING_STATUS_ACTIVE})
    return {"$and": clauses}


def _join_retrieved_documents(
    documents: list[str],
    metadatas: list[dict],
    *,
    item_type: str,
    current_chapter: Optional[int],
    limit: int,
) -> str:
    rows = []
    metadata_rows = metadatas or []
    for idx, doc in enumerate(documents or []):
        meta = metadata_rows[idx] if idx < len(metadata_rows) else {}
        if not doc or not str(doc).strip():
            continue
        if item_type == "foreshadowing" and (meta or {}).get("status") not in (None, FORESHADOWING_STATUS_ACTIVE):
            continue
        rows.append((str(doc).strip(), meta or {}))

    if item_type in {"foreshadowing", "plot_threads"}:
        rows = _prefer_current_window(rows, current_chapter)

    seen = set()
    selected = []
    for doc, _meta in rows:
        if doc in seen:
            continue
        seen.add(doc)
        selected.append(doc)
        if len(selected) >= limit:
            break
    return "\n".join(selected)


def _fallback_items(
    text: str,
    *,
    item_type: str,
    limit: int,
    current_chapter: Optional[int],
) -> list[str]:
    if item_type == "foreshadowing":
        return _fallback_foreshadowing(text, limit, current_chapter)
    if item_type == "plot_threads":
        return _fallback_plot_threads(text, limit, current_chapter)
    return parse_bullet_points(text)[-limit:]


def _fallback_foreshadowing(text: str, limit: int, current_chapter: Optional[int]) -> list[str]:
    items = _foreshadowing_items_from_text(text)
    if items:
        rows = []
        for item in items:
            if getattr(item, "status", FORESHADOWING_STATUS_ACTIVE) != FORESHADOWING_STATUS_ACTIVE:
                continue
            doc = getattr(item, "description", "") or getattr(item, "body", "") or item.name
            rows.append((doc, {"chapter": getattr(item, "chapter", 0), "importance": getattr(item, "importance", "")}))
        return [doc for doc, _meta in _slice_preferred_rows(rows, limit, current_chapter)]

    parsed = parse_bullet_points(text)
    rows = []
    for item in parsed:
        data = _json_dict(item)
        if data and data.get("status", FORESHADOWING_STATUS_ACTIVE) != FORESHADOWING_STATUS_ACTIVE:
            continue
        rows.append((item, {"chapter": _first_int(data, "chapter", "chapter_created") or 0}))
    return [doc for doc, _meta in _slice_preferred_rows(rows, limit, current_chapter)]


def _debt_label(item: ForeshadowingKnowledge) -> str:
    """Human label for the debt type stored in attributes (承诺-张力图谱).

    Plain foreshadowing has no debt_type and keeps the legacy "伏笔" label;
    extractor-tagged debts (悬念/打脸/目标) surface their kind so the planner
    knows what kind of tension is owed, not just that something is due.
    """
    debt_type = str((item.attributes or {}).get("debt_type") or DEBT_TYPE_FORESHADOWING)
    return DEBT_TYPE_LABELS.get(debt_type, DEBT_TYPE_LABELS[DEBT_TYPE_FORESHADOWING])


def _tension_rank(item: ForeshadowingKnowledge) -> int:
    """Scheduling priority by tension attribute, falling back to importance.

    tension is the debt-graph's dedicated urgency axis; when absent we reuse
    the existing importance rank so plain foreshadowing keeps its old ordering.
    """
    tension = str((item.attributes or {}).get("tension") or "").lower()
    if tension in _TENSION_RANKS:
        return _TENSION_RANKS[tension]
    return _importance_rank(item.importance)


_TENSION_RANKS = {"high": 0, "medium": 1, "low": 2}


def _append_due_foreshadowing_context(
    retrieved: str,
    source_text: str,
    *,
    current_chapter: Optional[int],
    limit: int,
    structured_items: Optional[list[ForeshadowingKnowledge]] = None,
) -> str:
    due_items = _due_debt_items(
        source_text,
        current_chapter=current_chapter,
        limit=limit,
        structured_items=structured_items,
    )
    if not due_items:
        return retrieved

    existing = retrieved or ""
    existing_names = {item.name for item in _foreshadowing_items_from_text(existing)}
    reminder_lines = []
    for item in due_items:
        if item.name in existing_names:
            continue
        overdue = bool(item.resolved_chapter and current_chapter and item.resolved_chapter < current_chapter)
        due_label = "逾期" if overdue else "本章到期"
        desc = item.description or item.body or item.name
        reminder_lines.append(
            f"- [{due_label}·{_debt_label(item)}] {item.name}: {desc} "
            f"(埋设章节: {item.chapter}, 目标兑现章节: {item.resolved_chapter})"
        )
    if not reminder_lines:
        return retrieved

    reminder = (
        "【债务/伏笔兑现提醒】\n"
        "以下悬念、打脸、目标或伏笔（债务）已到期或逾期。单章大纲智能体应优先规划其中少量兑现进入本章 "
        "key_events/required_changes；兑现前须保证其憋闷张力已充分积累。"
        "若本章不兑现，必须写明延后原因与新的目标章节，且一章不要集中兑现过多债务。\n"
        + "\n".join(reminder_lines)
    )
    return f"{existing}\n\n{reminder}".strip() if existing.strip() else reminder


def _due_debt_items(
    text: str,
    *,
    current_chapter: Optional[int],
    limit: int,
    structured_items: Optional[list[ForeshadowingKnowledge]] = None,
) -> list[ForeshadowingKnowledge]:
    """Debts due for payoff at/before current_chapter, highest tension first.

    Prefers the loss-less structured knowledge (carries attributes.debt_type /
    tension from the DB data column); falls back to re-parsing the living-doc
    markdown only when structured items are unavailable (keeps old call paths
    and tests working).
    """
    if not current_chapter:
        return []
    source = structured_items if structured_items else _foreshadowing_items_from_text(text)
    candidates = []
    for item in source:
        if item.status != FORESHADOWING_STATUS_ACTIVE:
            continue
        if not item.resolved_chapter or item.resolved_chapter > current_chapter:
            continue
        candidates.append(item)

    candidates.sort(
        key=lambda item: (
            item.resolved_chapter or current_chapter,
            _tension_rank(item),
            item.chapter,
            item.name,
        )
    )
    return candidates[:limit]


def _foreshadowing_items_from_text(text: str) -> list[ForeshadowingKnowledge]:
    if not text:
        return []

    markdown_items = knowledge_from_markdown("foreshadowing", text) if _looks_like_foreshadowing_markdown(text) else []
    items = [
        item if isinstance(item, ForeshadowingKnowledge) else ForeshadowingKnowledge(
            name=item.name,
            description=item.body,
            attributes=item.attributes,
            status=item.status,
            importance=item.importance,
        )
        for item in markdown_items
    ]
    if items:
        return items

    for data in _json_objects(text):
        item = _foreshadowing_item_from_dict(data, len(items) + 1)
        if item:
            items.append(item)
    if items:
        return items

    for raw in text.splitlines():
        data = _json_dict(raw.strip())
        if not data:
            continue
        item = _foreshadowing_item_from_dict(data, len(items) + 1)
        if item:
            items.append(item)
    return items


def _foreshadowing_item_from_dict(data: dict, index: int) -> ForeshadowingKnowledge | None:
    try:
        return ForeshadowingKnowledge(
            name=str(data.get("name") or data.get("id") or f"fs_{index:04d}"),
            description=str(data.get("description") or data.get("body") or ""),
            status=str(data.get("status", FORESHADOWING_STATUS_ACTIVE)),
            importance=str(data.get("importance", "")),
            chapter=int(data.get("chapter") or data.get("chapter_created") or 1),
            resolved_chapter=_first_int(data, "resolved_chapter", "target_chapter", "回收章节", "收回章节"),
            cancelled_chapter=_first_int(data, "cancelled_chapter"),
        )
    except (TypeError, ValueError):
        return None


def _json_objects(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except Exception:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _importance_rank(importance: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(str(importance).lower(), 1)


def _looks_like_foreshadowing_markdown(text: str) -> bool:
    return "[ID:" in text or "## 活跃伏笔" in text or "## 已回收伏笔" in text or "## 已作废伏笔" in text


def _fallback_plot_threads(text: str, limit: int, current_chapter: Optional[int]) -> list[str]:
    rows = []
    for item in parse_bullet_points(text):
        data = _json_dict(item)
        status = str(data.get("status", "active")) if data else "active"
        if status not in ("active", "ongoing", "open"):
            continue
        rows.append((
            item,
            {"chapter": _first_int(data, "chapter_updated", "chapter_created", "chapter", "last_chapter") or 0},
        ))
    return [doc for doc, _meta in _slice_preferred_rows(rows, limit, current_chapter)]


def _slice_preferred_rows(
    rows: list[tuple[str, dict]],
    limit: int,
    current_chapter: Optional[int],
) -> list[tuple[str, dict]]:
    ordered = _prefer_current_window(rows, current_chapter)
    if current_chapter:
        return ordered[:limit]
    return ordered[-limit:]


def _prefer_current_window(
    rows: list[tuple[str, dict]],
    current_chapter: Optional[int],
) -> list[tuple[str, dict]]:
    if not current_chapter:
        return rows
    min_chapter = max(1, current_chapter - VECTOR_ACTIVE_CONTEXT_RECENT_CHAPTER_WINDOW)
    recent = []
    distant = []
    for row in rows:
        chapter = _metadata_chapter(row[1])
        if chapter == 0 or chapter >= min_chapter:
            recent.append(row)
        else:
            distant.append(row)
    return recent + distant


def _metadata_chapter(meta: dict) -> int:
    return _first_int(meta, "chapter", "chapter_updated", "chapter_created", "last_chapter") or 0


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
