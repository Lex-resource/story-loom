"""Deterministic ranking helpers for novel-memory recall.

These helpers deliberately know nothing about SQLAlchemy or the recall
workflow.  The service owns candidate retrieval; this module owns the stable
ordering and projection rules applied to those candidates.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _recall_terms(value: str) -> set[str]:
    """Extract deterministic Latin tokens and CJK bigrams for local ranking."""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    terms = set(re.findall(r"[a-z0-9_]+", normalized))
    cjk = "".join(re.findall(r"[\u3400-\u9fff]", normalized))
    terms.update(cjk[index:index + 2] for index in range(max(0, len(cjk) - 1)))
    if not terms and normalized.strip():
        terms.add(normalized.strip())
    return {term for term in terms if term}


def lexical_recall_score(query_text: str, content: str) -> float:
    """Score text overlap without making lexical search authoritative."""
    query = unicodedata.normalize("NFKC", str(query_text or "")).casefold().strip()
    candidate = unicodedata.normalize("NFKC", str(content or "")).casefold().strip()
    if not query or not candidate:
        return 0.0
    query_terms = _recall_terms(query)
    candidate_terms = _recall_terms(candidate)
    if not query_terms or not candidate_terms:
        return 0.0
    overlap = len(query_terms & candidate_terms) / len(query_terms)
    phrase_bonus = 0.75 if query in candidate else 0.0
    return round(overlap + phrase_bonus, 6)


def rank_recall_items(
    items: list[Any],
    query_text: str,
    *,
    limit: int,
    text_getter,
) -> list[Any]:
    """Rank a bounded database candidate pool by relevance and recency."""
    indexed = list(enumerate(items))

    def sort_key(pair: tuple[int, Any]) -> tuple[float, int, int, int]:
        index, item = pair
        score = lexical_recall_score(query_text, text_getter(item))
        source_chapter = int(getattr(item, "source_chapter", 0) or 0)
        version = int(getattr(item, "version", 0) or 0)
        return (-score, -source_chapter, -version, index)

    indexed.sort(key=sort_key)
    return [item for _index, item in indexed[:max(0, limit)]]


def version_key(item: Any) -> tuple[int, int]:
    """Order persisted projections by chapter and version."""
    return (
        int(getattr(item, "source_chapter", 0) or 0),
        int(getattr(item, "version", 0) or 0),
    )


def latest_atoms_by_key(items: list[Any] | tuple[Any, ...] | None) -> list[Any]:
    """Expose one latest projection per memory key while retaining audit rows."""
    selected: dict[str, Any] = {}
    order: list[str] = []
    for index, item in enumerate(items or []):
        memory_key = str(getattr(item, "memory_key", "") or "").strip()
        if not memory_key:
            memory_key = f"statement:{str(getattr(item, 'statement', '') or '').strip()}:{index}"
        current = selected.get(memory_key)
        if current is None:
            order.append(memory_key)
            selected[memory_key] = item
            continue
        if version_key(item) > version_key(current):
            selected[memory_key] = item
    return [selected[key] for key in order]


def latest_scene_blocks(items: list[Any] | tuple[Any, ...] | None) -> list[Any]:
    """Keep the current scene state for each scope in an agent prompt."""
    selected: dict[tuple[str, str], Any] = {}
    order: list[tuple[str, str]] = []
    for index, item in enumerate(items or []):
        key = (
            str(getattr(item, "scope_type", "") or ""),
            str(getattr(item, "scope_key", "") or f"scene-{index}"),
        )
        current = selected.get(key)
        if current is None:
            order.append(key)
            selected[key] = item
            continue
        if version_key(item) > version_key(current):
            selected[key] = item
    return [selected[key] for key in order]


# Keep private aliases available to callers that imported the old helpers.
_version_key = version_key
_latest_atoms_by_key = latest_atoms_by_key
_latest_scene_blocks = latest_scene_blocks

