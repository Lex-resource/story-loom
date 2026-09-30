"""Helpers for reading the best available chapter text across pipeline stages."""

from __future__ import annotations

from typing import Any


def effective_chapter_content(chapter: Any) -> str:
    """Return the most authoritative non-empty text currently stored on a chapter row.

    Published content is preferred, with the editable and draft projections as
    fallbacks. Mainline ``Chapter`` and character-branch chapter rows expose
    the same fields, so callers can share this ordering without silently
    dropping context when a row has not reached publish yet.
    """
    if chapter is None:
        return ""
    return str(
        getattr(chapter, "content", None)
        or getattr(chapter, "edited_content", None)
        or getattr(chapter, "draft_content", None)
        or ""
    )
