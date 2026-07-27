from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import ChapterOutline, Novel
from services import living_docs
from services.knowledge_types import PlotThreadKnowledge
from services.short_story_living_doc_builders import (
    as_list,
    build_characters,
    build_foreshadowing,
    build_world_rules,
    format_act_outline,
    format_global_outline,
    item_name,
    outline_title,
)


async def sync_short_story_living_docs(
    db: AsyncSession,
    novel: Novel,
    *,
    chapter_index: int | None = None,
) -> None:
    """Persist baseline Living Docs for short stories from skeleton outlines.

    Short-story projects freeze the dynamic extractor, but the UI and later
    chapters still need structured living docs. This deterministic sync uses
    the already-approved skeleton and chapter outlines, avoiding another LLM
    call while still producing character/world/plot/outline documents.
    """
    outline = novel.outline or {}
    if not isinstance(outline, dict):
        return

    project_id = str(novel.id)
    title = outline_title(novel, outline)

    characters = await _merge_with_existing(
        project_id, "character_state", build_characters(outline), db
    )
    world_rules = await _merge_with_existing(
        project_id, "world_state", build_world_rules(outline), db
    )
    plot_threads = await _merge_with_existing(
        project_id, "plot_threads", await _build_plot_threads(db, novel, outline), db
    )
    foreshadowing = await _merge_with_existing(
        project_id, "foreshadowing", build_foreshadowing(outline), db
    )
    await living_docs.write_knowledge(
        project_id, "character_state", characters, db, check_readonly=False, auto_commit=False
    )
    await living_docs.write_knowledge(
        project_id, "world_state", world_rules, db, check_readonly=False, auto_commit=False
    )
    await living_docs.write_knowledge(
        project_id, "plot_threads", plot_threads, db, check_readonly=False, auto_commit=False
    )
    await living_docs.write_knowledge(
        project_id, "foreshadowing", foreshadowing, db, check_readonly=False, auto_commit=False
    )

    await living_docs.write_doc(project_id, "global_outline", format_global_outline(title, outline), db)
    await living_docs.write_doc(project_id, "act_outline", format_act_outline(title, outline), db)

    if chapter_index is not None:
        for doc_type in (
            "character_state",
            "world_state",
            "plot_threads",
            "foreshadowing",
            "global_outline",
            "act_outline",
        ):
            await living_docs.snapshot_doc(project_id, chapter_index, doc_type, db)


async def _merge_with_existing(
    project_id: str,
    doc_type: str,
    baseline_items: list[Any],
    db: AsyncSession,
) -> list[Any]:
    existing_items = await living_docs.read_knowledge(project_id, doc_type, db)
    merged = {item.name: item for item in baseline_items}
    for item in existing_items:
        # Dynamic extractor output is more specific than skeleton-derived
        # baseline data, so keep existing records when names collide.
        merged[item.name] = item
    return list(merged.values())


async def _build_plot_threads(
    db: AsyncSession,
    novel: Novel,
    outline: dict[str, Any],
) -> list[PlotThreadKnowledge]:
    threads: list[PlotThreadKnowledge] = []
    for idx, raw in enumerate(as_list(outline.get("故事阶段")), start=1):
        name = item_name(raw, "幕名", "阶段名称", "名称", "name", fallback=f"第{idx}幕")
        if isinstance(raw, dict):
            progress = raw.get("progress") or raw.get("主要推进") or raw.get("概要") or raw.get("核心冲突") or ""
            next_step = raw.get("下一步") or raw.get("next_step") or ""
        else:
            progress = str(raw)
            next_step = ""
        threads.append(PlotThreadKnowledge(name=name, progress=str(progress), next_step=str(next_step)))

    result = await db.execute(
        select(ChapterOutline)
        .where(ChapterOutline.project_id == novel.id)
        .order_by(ChapterOutline.chapter_index)
    )
    chapter_lines: list[str] = []
    for row in result.scalars().all():
        data = row.outline or {}
        if not isinstance(data, dict):
            continue
        summary = data.get("summary") or data.get("概要") or ""
        if summary:
            title = data.get("title") or data.get("标题") or f"第{row.chapter_index}章"
            chapter_lines.append(f"第{row.chapter_index}章《{title}》: {summary}")
    if chapter_lines:
        threads.append(PlotThreadKnowledge(name="章节推进", progress="\n".join(chapter_lines)))
    return threads
