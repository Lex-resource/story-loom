"""Pure helpers for assembling short-story manuscript context."""

from __future__ import annotations


def build_short_manuscript_context(chapters: list, *, max_chars: int) -> str:
    """Render all available prior short-story sections within a hard budget."""
    blocks = []
    for chapter in chapters:
        content = chapter.content or chapter.edited_content or chapter.draft_content or ""
        if not content:
            continue
        title = chapter.title or f"第{chapter.chapter_index}节"
        blocks.append(f"【第{chapter.chapter_index}节 {title}】\n{content.strip()}")

    rendered = "\n\n".join(blocks)
    if len(rendered) <= max_chars:
        return rendered
    return "【前文开头因上下文预算已截断】\n" + rendered[-max_chars:]
