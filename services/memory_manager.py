"""Layered memory context assembly shared by generation and extraction."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import NOVEL_FORMAT_ZHIHU_SHORT
from agents.pipeline_context import PipelineContext
from config import settings
from models.novel import Chapter, Novel
from services.chapter_continuity import build_chapter_handoff
from services.context_compaction import context_budget_for
from services.novel_constants import (
    CHAPTER_SUMMARY_PREVIEW_CHARS,
    PREVIOUS_CHAPTER_ENDING_CHARS_FOR_CONTEXT,
    SHORT_MANUSCRIPT_CONTEXT_MAX_CHARS,
    SHORT_TERM_MEMORY_WINDOW,
)
from services.novel_memory_recall import (
    merge_layered_context,
    narrative_index_chars_for,
    recall_novel_memory,
)
from services.narrative_index import format_narrative_context
from services.pipeline_config_service import NovelFormatPolicy
from services.short_story_context import (
    TRUNCATION_MARKER,
    build_short_manuscript_context,
    short_block_prefix,
)


import logging

logger = logging.getLogger(__name__)


def _build_memory_recall_query(query_text: str, outline_data: dict | None) -> str:
    """Build a bounded lexical/vector query from the current agent request."""
    parts = [str(query_text or "").strip()]
    if isinstance(outline_data, dict):
        for key in (
            "title",
            "plotline",
            "narrative_stage",
            "characters_involved",
            "key_events",
            "required_events",
            "foreshadowing_actions",
            "unresolved_threads",
        ):
            value = outline_data.get(key)
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
            elif value:
                parts.append(str(value))
    return " ".join(part for part in parts if part)[:2000]


def _hybrid_recall_suppressed() -> bool:
    """研究变体是否关闭混合召回（把向量检索作为实验变量）。

    生产（A28）不抑制，由 `ENABLE_NOVEL_HYBRID_RECALL` 单独决定。
    """
    from services.version_surface import NO_OVERRIDE, research_override

    override = research_override("hybrid_recall_suppressed")
    return bool(override) if override is not NO_OVERRIDE else False


# btrim 与 Python str.strip 的空白集合不完全一致，估算可能偏差几个字符；
# 预算额外预留一段余量。极端情况下（估算偏小导致后缀没攒够 max_chars）
# 再退回整表加载，保证输出与"一次性全量渲染"逐字节一致。
_SHORT_SUFFIX_SLACK_CHARS = 512


def _pick_short_suffix_start(
    blocks_meta: list[tuple[int, str | None, int]],
    *,
    max_chars: int,
    slack: int = _SHORT_SUFFIX_SLACK_CHARS,
) -> tuple[int, bool]:
    """从尾部累计块长度，返回进入预算所需的最小连续章节号与是否达标。

    输出只取决于整份手稿渲染后的最后 max_chars 字符，因此任何"包含足够
    字符数的连续后缀"都能渲染出与全量渲染一致的结果。
    """
    target = max_chars + slack
    total = 0
    reached_target = False
    start_index = blocks_meta[-1][0]
    for pos in range(len(blocks_meta) - 1, -1, -1):
        block_index, title, content_len = blocks_meta[pos]
        total += len(short_block_prefix(block_index, title)) + content_len
        if pos < len(blocks_meta) - 1:
            total += 2  # 块间 "\n\n" 分隔符
        start_index = block_index
        if total >= target:
            reached_target = True
            break
    return start_index, reached_target


def _rendered_short_blocks_len(chapters: list) -> int:
    blocks = []
    for chapter in chapters:
        content = chapter.content or chapter.edited_content or chapter.draft_content or ""
        if not content:
            continue
        blocks.append(
            len(short_block_prefix(chapter.chapter_index, chapter.title))
            + len(content.strip())
        )
    if not blocks:
        return 0
    return sum(blocks) + 2 * (len(blocks) - 1)


async def _load_short_manuscript_suffix(
    db: AsyncSession,
    project_id: uuid.UUID,
    chapter_index: int,
    *,
    max_chars: int,
) -> list[Chapter]:
    """返回构建短篇手稿上下文所需的"尾部"章节，正文不整表加载。

    第一条查询只取元数据（chapter_index/title/正文长度，不含 content TEXT），
    第二条只拉取后缀区间的正文；全书体量远小于预算时行为与全量加载一致。
    """
    effective_content = func.coalesce(
        func.nullif(Chapter.content, ""),
        func.nullif(Chapter.edited_content, ""),
        func.nullif(Chapter.draft_content, ""),
    )
    base_where = (
        Chapter.novel_id == project_id,
        Chapter.chapter_index < chapter_index,
    )
    meta_result = await db.execute(
        select(
            Chapter.chapter_index,
            Chapter.title,
            func.length(func.btrim(effective_content)).label("content_len"),
        )
        .where(*base_where)
        .order_by(Chapter.chapter_index.asc())
    )
    blocks_meta = [
        (row.chapter_index, row.title, row.content_len or 0)
        for row in meta_result.all()
        if (row.content_len or 0) > 0
    ]
    if not blocks_meta:
        return []

    start_index, reached_target = _pick_short_suffix_start(
        blocks_meta, max_chars=max_chars
    )

    suffix_result = await db.execute(
        select(Chapter)
        .where(*base_where, Chapter.chapter_index >= start_index)
        .order_by(Chapter.chapter_index.asc())
    )
    st_chapters = list(suffix_result.scalars().all())

    if reached_target and _rendered_short_blocks_len(st_chapters) < max_chars:
        # 估算偏小的极端兜底：整表加载，保证输出与旧实现一致
        all_result = await db.execute(
            select(Chapter).where(*base_where).order_by(Chapter.chapter_index.asc())
        )
        return list(all_result.scalars().all())
    return st_chapters


class MemoryManager:
    @staticmethod
    async def _load_chapter_context(
        db: AsyncSession,
        project_id: uuid.UUID,
        chapter_index: int,
        agent_type: str,
    ) -> dict[str, str | Novel | bool]:
        prev_result = await db.execute(
            select(Chapter).where(
                Chapter.novel_id == project_id,
                Chapter.chapter_index == chapter_index - 1,
            )
        )
        prev_chapter = prev_result.scalar_one_or_none()
        previous_ending = (
            prev_chapter.content[-PREVIOUS_CHAPTER_ENDING_CHARS_FOR_CONTEXT:]
            if prev_chapter and prev_chapter.content
            else ""
        )

        novel_res = await db.execute(select(Novel).where(Novel.id == project_id))
        novel = novel_res.scalar_one_or_none()
        policy = NovelFormatPolicy.from_format(novel.novel_format if novel else None)
        is_short_story = policy.bypass_short_term_memory_window

        st_chapters: list[Chapter]
        short_term_summaries: list[str] = []
        full_manuscript_context = ""
        if is_short_story:
            # 短篇上下文按预算取尾：元数据先行（不含 content TEXT），只拉取
            # 进入预算所需的尾部章节，避免每次 agent 调用整表加载全书。
            st_chapters = await _load_short_manuscript_suffix(
                db,
                project_id,
                chapter_index,
                max_chars=SHORT_MANUSCRIPT_CONTEXT_MAX_CHARS,
            )
            full_manuscript_context = build_short_manuscript_context(
                st_chapters,
                max_chars=SHORT_MANUSCRIPT_CONTEXT_MAX_CHARS,
            )
        else:
            st_query = select(Chapter).where(
                Chapter.novel_id == project_id,
                Chapter.chapter_index < chapter_index,
                Chapter.chapter_index >= max(1, chapter_index - SHORT_TERM_MEMORY_WINDOW),
            ).order_by(Chapter.chapter_index.asc())
            st_result = await db.execute(st_query)
            st_chapters = list(st_result.scalars().all())
            for chapter in st_chapters:
                chapter_summary = ""
                if chapter.outline and isinstance(chapter.outline, dict):
                    chapter_summary = chapter.outline.get("summary", "")
                elif chapter.outline and isinstance(chapter.outline, str):
                    try:
                        outline = json.loads(chapter.outline)
                        chapter_summary = outline.get("summary", "")
                    except Exception as exc:
                        logger.warning(
                            f"[Context WARN] Failed to parse chapter {chapter.chapter_index} outline JSON: {exc}"
                        )
                if not chapter_summary and chapter.draft_content:
                    chapter_summary = (
                        chapter.draft_content[:CHAPTER_SUMMARY_PREVIEW_CHARS].strip() + "..."
                    )
                short_term_summaries.append(
                    f"第{chapter.chapter_index}章《{chapter.title}》梗概: {chapter_summary}"
                )

        handoff = await build_chapter_handoff(
            db,
            project_id,
            chapter_index,
            previous_ending=previous_ending,
        )
        handoff_limit = (
            context_budget_for(agent_type).handoff_chars
        )
        handoff_context = (
            handoff.to_compact_prompt(max_chars=handoff_limit)
        )
        return {
            "novel": novel,
            "previous_ending": previous_ending,
            "chapter_handoff": handoff,
            "chapter_handoff_context": handoff_context,
            "short_term_context": "\n".join(short_term_summaries),
            "full_manuscript_context": full_manuscript_context,
            "is_short_story": is_short_story,
        }

    @staticmethod
    async def _load_knowledge_context(
        db: AsyncSession,
        project_id: uuid.UUID,
        chapter_index: int,
        query_text: str,
        outline_data: dict | None,
        novel: Novel | None,
    ) -> dict:
        from services.character_context import build_planner_manifest_context
        from services.outline_service import extract_genre_style

        genre, style = extract_genre_style(
            novel.outline
            if novel and novel.outline and isinstance(novel.outline, dict)
            else None
        )
        return {
            "rag_context": {
                "world_state": "",
                "character_state": "",
                "foreshadowing": "",
                "plot_threads": "",
                "chapter_extracts": "",
            },
            "all_knowledge": {},
            "world_state": "",
            "character_state": "",
            "foreshadowing": "",
            "plot_threads": "",
            "character_manifest_context": await build_planner_manifest_context(
                db,
                project_id,
            ),
            "genre": genre,
            "style": style,
        }

    @staticmethod
    async def _load_novel_memory_context(
        db: AsyncSession,
        project_id: uuid.UUID,
        chapter_index: int,
        agent_type: str,
        query_text: str = "",
        outline_data: dict | None = None,
        previous_ending: str = "",
        handoff_context: str = "",
    ) -> str:
        if settings.ENABLE_NOVEL_MEMORY_RECALL:
            recall_query = " ".join(
                part
                for part in (
                    query_text,
                    str(previous_ending or "")[-900:],
                    str(handoff_context or "")[:900],
                )
                if part
            )
            recall = await recall_novel_memory(
                db,
                project_id=project_id,
                chapter_index=chapter_index,
                agent_type=agent_type,
                query_text=_build_memory_recall_query(recall_query, outline_data),
                # A5 isolates the gated quality-agent variable from A4's
                # retrieval variable. Production keeps the configured flag.
                include_vector=(
                    settings.ENABLE_NOVEL_HYBRID_RECALL
                    and not _hybrid_recall_suppressed()
                ),
            )
            if recall.injected_atoms:
                # 命中簿记在调用方落库:recall 保持只读,簿记失败不抛错。
                from services.novel_memory_lifecycle import record_recall_hits

                await record_recall_hits(db, chapter_index, recall.injected_atoms)
            return recall.context
        return ""
    @staticmethod
    async def _load_narrative_index_context(
        db: AsyncSession,
        project_id: uuid.UUID,
        chapter_index: int,
        agent_type: str,
    ) -> str:
        if not settings.ENABLE_NOVEL_NARRATIVE_INDEX:
            return ""
        from models.narrative_index import NarrativeIndexEntry

        rows = list((await db.scalars(
            select(NarrativeIndexEntry).where(
                NarrativeIndexEntry.project_id == project_id,
                NarrativeIndexEntry.branch_id.is_(None),
                NarrativeIndexEntry.storyline_id == "main",
                NarrativeIndexEntry.status == "accepted",
                NarrativeIndexEntry.is_active.is_(True),
                NarrativeIndexEntry.chapter_index <= chapter_index,
            ).order_by(
                NarrativeIndexEntry.chapter_index.desc(),
                NarrativeIndexEntry.sequence.asc(),
            ).limit(24)
        )).all())
        return format_narrative_context(
            rows,
            max_chars=narrative_index_chars_for(agent_type),
            agent_type=agent_type,
        )

    @staticmethod
    async def get_context(
        db: AsyncSession,
        project_id: uuid.UUID,
        chapter_index: int,
        query_text: str,
        outline_data: dict | None = None,
        agent_type: str = "writer",
    ) -> dict:
        chapter_context = await MemoryManager._load_chapter_context(
            db, project_id, chapter_index, agent_type
        )
        novel = chapter_context["novel"]
        knowledge_context = await MemoryManager._load_knowledge_context(
            db,
            project_id,
            chapter_index,
            query_text,
            outline_data,
            novel,
        )
        novel_memory_context = await MemoryManager._load_novel_memory_context(
            db,
            project_id,
            chapter_index,
            agent_type,
            query_text=query_text,
            outline_data=outline_data,
            previous_ending=chapter_context["previous_ending"],
            handoff_context=chapter_context["chapter_handoff_context"],
        )
        narrative_index_context = await MemoryManager._load_narrative_index_context(
            db, project_id, chapter_index, agent_type
        )
        character_manifest_context = knowledge_context["character_manifest_context"]
        if agent_type == "planner":
            novel_memory_context = merge_layered_context(
                character_manifest_context,
                novel_memory_context,
                max_chars=context_budget_for("planner").manifest_chars,
            )
            character_manifest_context = ""
        rag_context = knowledge_context["rag_context"]
        all_knowledge = knowledge_context["all_knowledge"]

        previous_source_chapter = chapter_index - 1 if chapter_index > 1 else None
        context_sources = {
            "previous_ending": {
                "source_ref": (
                    f"chapter:{previous_source_chapter}:published"
                    if previous_source_chapter
                    else "chapter:previous:unknown"
                ),
                "source_chapter": previous_source_chapter,
                "authority": "published" if previous_source_chapter else "unknown",
            },
            "chapter_handoff_context": {
                "source_ref": (
                    f"chapter:{previous_source_chapter}:handoff"
                    if previous_source_chapter
                    else "chapter:previous:unknown"
                ),
                "source_chapter": previous_source_chapter,
                "authority": "accepted" if previous_source_chapter else "unknown",
            },
            "chapter_contract_context": {
                "source_ref": f"chapter:{chapter_index}:contract",
                "source_chapter": chapter_index,
                "authority": "accepted",
            },
            "character_manifest_context": {
                "source_ref": "character_manifest",
                "authority": "frozen_or_accepted",
            },
            "novel_memory_context": {
                "source_ref": "novel_memory:recall",
                "authority": "accepted_with_candidate_boundary",
            },
            "narrative_index_context": {
                "source_ref": "narrative_index:accepted",
                "source_chapter": chapter_index,
                "authority": "published_projection",
            },
            "vector_context": {
                "source_ref": "chroma:chapter_extracts",
                "authority": "retrieved_advisory",
            },
        }

        return {
            "agent_type": agent_type,
            "previous_ending": chapter_context["previous_ending"],
            "chapter_handoff": chapter_context["chapter_handoff"].to_dict(),
            "chapter_handoff_context": chapter_context["chapter_handoff_context"],
            "short_term_context": chapter_context["short_term_context"],
            "full_manuscript_context": chapter_context["full_manuscript_context"],
            "world_state": rag_context["world_state"],
            "character_state": rag_context["character_state"],
            "foreshadowing": rag_context["foreshadowing"],
            "plot_threads": rag_context["plot_threads"],
            "vector_context": rag_context.get("chapter_extracts", ""),
            "novel_memory_context": novel_memory_context,
            "narrative_index_context": narrative_index_context,
            "genre": knowledge_context["genre"],
            "style": knowledge_context["style"],
            "raw_world_state": knowledge_context["world_state"],
            "raw_character_state": knowledge_context["character_state"],
            "character_manifest_context": character_manifest_context,
            "character_card_context": "",
            "raw_foreshadowing": knowledge_context["foreshadowing"],
            "raw_plot_threads": knowledge_context["plot_threads"],
            "novel_format": novel.novel_format if novel else "",
            "context_sources": context_sources,
            "knowledge": {
                "world_state": all_knowledge.get("world_state", []),
                "character_state": all_knowledge.get("character_state", []),
                "foreshadowing": all_knowledge.get("foreshadowing", []),
                "plot_threads": all_knowledge.get("plot_threads", []),
            },
            "total_chapters": novel.target_chapters if novel else 0,
        }

    @staticmethod
    async def get_pipeline_context(
        db: AsyncSession,
        project_id: uuid.UUID,
        chapter_index: int,
        query_text: str,
        outline_data: dict | None = None,
        agent_type: str = "writer",
    ) -> PipelineContext:
        memory = await MemoryManager.get_context(
            db,
            project_id,
            chapter_index,
            query_text,
            outline_data,
            agent_type,
        )
        return PipelineContext.from_memory(
            str(project_id),
            chapter_index,
            memory,
            agent_type=agent_type,
        )
