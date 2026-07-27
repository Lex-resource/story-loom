"""Creative-profile defaults shared by project creation and legacy reads."""

from __future__ import annotations

from typing import Any

from agents.constants import NOVEL_FORMAT_LONG_WEBNOVEL, NOVEL_FORMAT_ZHIHU_SHORT

STORY_LENGTH_SHORT = "short"
STORY_LENGTH_LONG = "long"

SHORT_DEFAULT_SECTIONS = 3
SHORT_DEFAULT_TOTAL_WORDS = 12_000
LONG_DEFAULT_CHAPTERS = 100
LONG_DEFAULT_WORDS_PER_CHAPTER = 3_000


def normalize_creative_profile(
    profile: dict[str, Any] | None,
    *,
    novel_format: str | None = None,
    target_chapters: int | None = None,
    word_count_per_chapter: int | None = None,
) -> dict[str, Any]:
    source = profile if isinstance(profile, dict) else {}
    inferred_short = novel_format == NOVEL_FORMAT_ZHIHU_SHORT
    story_length = source.get("story_length") or (
        STORY_LENGTH_SHORT if inferred_short else STORY_LENGTH_LONG
    )
    if story_length not in {STORY_LENGTH_SHORT, STORY_LENGTH_LONG}:
        story_length = STORY_LENGTH_LONG

    is_short = story_length == STORY_LENGTH_SHORT
    sections = _positive_int(
        source.get("target_chapters", target_chapters),
        SHORT_DEFAULT_SECTIONS if is_short else LONG_DEFAULT_CHAPTERS,
    )
    words_per_chapter = _positive_int(
        source.get("word_count_per_chapter", word_count_per_chapter),
        SHORT_DEFAULT_TOTAL_WORDS // sections if is_short else LONG_DEFAULT_WORDS_PER_CHAPTER,
    )
    total_word_count = _positive_int(
        source.get("total_word_count"),
        sections * words_per_chapter,
    )

    return {
        "story_length": story_length,
        "publishing_mode": source.get("publishing_mode") or ("complete" if is_short else "serial"),
        "prose_style": source.get("prose_style") or ("platform_story" if is_short else "web_novel"),
        "point_of_view": source.get("point_of_view") or ("first" if is_short else "third"),
        "total_word_count": total_word_count,
        "target_chapters": sections,
        "word_count_per_chapter": words_per_chapter,
    }


def workflow_format_for_profile(profile: dict[str, Any]) -> str:
    return (
        NOVEL_FORMAT_ZHIHU_SHORT
        if profile.get("story_length") == STORY_LENGTH_SHORT
        else NOVEL_FORMAT_LONG_WEBNOVEL
    )


def _positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback
