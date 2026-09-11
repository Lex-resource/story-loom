"""Pure helpers for assembling short-story manuscript context."""

from __future__ import annotations

TRUNCATION_MARKER = "【前文开头因上下文预算已截断】"


def short_block_prefix(chapter_index: int, title: str | None) -> str:
    """单个手稿块的固定前缀（memory_manager 的预算估算与其保持同一实现）。"""
    resolved = title or f"第{chapter_index}节"
    return f"【第{chapter_index}节 {resolved}】\n"


def build_short_manuscript_context(chapters: list, *, max_chars: int) -> str:
    """Render all available prior short-story sections within a hard budget."""
    blocks = []
    for chapter in chapters:
        content = chapter.content or chapter.edited_content or chapter.draft_content or ""
        if not content:
            continue
        blocks.append(f"{short_block_prefix(chapter.chapter_index, chapter.title)}{content.strip()}")

    rendered = "\n\n".join(blocks)
    if len(rendered) <= max_chars:
        return rendered
    return TRUNCATION_MARKER + "\n" + rendered[-max_chars:]
