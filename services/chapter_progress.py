"""Chapter progress helpers shared by API services and worker jobs."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Optional

from services.novel_constants import DEFAULT_TARGET_CHAPTERS
from services.pipeline_types import ChapterStatus


ADVANCEABLE_CHAPTER_STATUSES = frozenset(
    {
        ChapterStatus.PUBLISHED,
        ChapterStatus.VALIDATED,
        ChapterStatus.POST_PROCESSING,
    }
)


def is_frozen(chapter) -> bool:
    """Return True if a chapter is published and therefore immutable.

    Published chapters are terminal in the serialized-release model: readers
    have already consumed them, so no revision pass may ever touch them. Any
    volume-level rewrite flow must skip chapters where this returns True.
    """
    return getattr(chapter, "status", None) == ChapterStatus.PUBLISHED


def chapter_status_map(chapters: Iterable[tuple[int, str | None]]) -> dict[int, str | None]:
    return {chapter_index: status for chapter_index, status in chapters}


def find_next_writable_chapter(
    chapters: Iterable[tuple[int, str | None]],
    target_chapters: Optional[int],
) -> int:
    """Return the next chapter index that still needs generation work."""
    statuses = chapter_status_map(chapters)
    target_limit = (target_chapters or DEFAULT_TARGET_CHAPTERS) + 1

    for chapter_index in range(1, target_limit):
        status = statuses.get(chapter_index)
        if status is None or status not in ADVANCEABLE_CHAPTER_STATUSES:
            return chapter_index

    return max(list(statuses.keys()) or [0]) + 1


def all_target_chapters_published(
    chapters: Iterable[tuple[int, str | None]],
    target_chapters: Optional[int],
) -> bool:
    if not target_chapters:
        return False

    statuses = chapter_status_map(chapters)
    for chapter_index in range(1, target_chapters + 1):
        if statuses.get(chapter_index) != ChapterStatus.PUBLISHED:
            return False
    return True
