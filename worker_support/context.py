from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import NOVEL_FORMAT_ZHIHU_SHORT
from agents.pipeline_context import PipelineContext
from services import living_docs
from services.novel_constants import (
    CHAPTER_SUMMARY_PREVIEW_CHARS,
    PREVIOUS_CHAPTER_ENDING_CHARS_FOR_CONTEXT,
    SHORT_TERM_MEMORY_WINDOW,
    SHORT_MANUSCRIPT_CONTEXT_MAX_CHARS,
)
from services.pipeline_config_service import NovelFormatPolicy
from services.pipeline_commands import get_intervention_prompt
from services.vector_store import index_settings, retrieve_setting_context
from services.short_story_context import build_short_manuscript_context
from models.novel import Chapter, Novel


class MemoryManager:
    @staticmethod
    async def get_context(
        db: AsyncSession,
        project_id: uuid.UUID,
        chapter_index: int,
        query_text: str,
        outline_data: dict | None = None,
    ) -> dict:
        prev_result = await db.execute(
            select(Chapter).where(Chapter.novel_id == project_id, Chapter.chapter_index == chapter_index - 1)
        )
        prev_chapter = prev_result.scalar_one_or_none()
        previous_ending = prev_chapter.content[-PREVIOUS_CHAPTER_ENDING_CHARS_FOR_CONTEXT:] if prev_chapter and prev_chapter.content else ""

        # Peek (not consume) so that all pipeline phases of the same chapter
        # see the same intervention. The prompt is consumed at the end of a
        # successful chapter run by ChapterPipelineRunner.run_all.
        intervention = await get_intervention_prompt(db, project_id)

        novel_res = await db.execute(select(Novel).where(Novel.id == project_id))
        novel = novel_res.scalar_one_or_none()
        _policy = NovelFormatPolicy.from_format(novel.novel_format if novel else None)
        is_short_story = _policy.bypass_short_term_memory_window

        st_query = select(Chapter).where(
            Chapter.novel_id == project_id,
            Chapter.chapter_index < chapter_index,
        ).order_by(Chapter.chapter_index.asc())

        if not is_short_story:
            st_query = st_query.where(Chapter.chapter_index >= max(1, chapter_index - SHORT_TERM_MEMORY_WINDOW))

        st_result = await db.execute(st_query)
        st_chapters = st_result.scalars().all()
        short_term_summaries = []
        full_manuscript_context = ""
        if is_short_story:
            full_manuscript_context = build_short_manuscript_context(
                st_chapters,
                max_chars=SHORT_MANUSCRIPT_CONTEXT_MAX_CHARS,
            )
        for ch in st_chapters:
            if is_short_story:
                continue

            ch_summary = ""
            if ch.outline and isinstance(ch.outline, dict):
                ch_summary = ch.outline.get("summary", "")
            elif ch.outline and isinstance(ch.outline, str):
                try:
                    o_dict = json.loads(ch.outline)
                    ch_summary = o_dict.get("summary", "")
                except Exception as je:
                    print(f"[Context WARN] Failed to parse chapter {ch.chapter_index} outline JSON: {je}")
            if not ch_summary and ch.draft_content:
                ch_summary = ch.draft_content[:CHAPTER_SUMMARY_PREVIEW_CHARS].strip() + "..."
            short_term_summaries.append(f"第{ch.chapter_index}章《{ch.title}》梗概: {ch_summary}")
        short_term_context = "\n".join(short_term_summaries)

        all_docs = await living_docs.read_all_docs(str(project_id), db)
        world_state = all_docs.get("world_state", "")
        character_state = all_docs.get("character_state", "")
        foreshadowing = all_docs.get("foreshadowing", "")
        plot_threads = all_docs.get("plot_threads", "")

        # Batch-read knowledge for all 4 knowledge doc types in a single query
        # (previously 4 separate read_knowledge calls hitting the same table).
        all_knowledge = await living_docs.read_all_knowledge(str(project_id), db)

        await index_settings(
            project_id=str(project_id),
            character_state=character_state,
            world_state=world_state,
            foreshadowing=foreshadowing,
            plot_threads=plot_threads,
        )

        from services.outline_service import resolve_protagonist_name, extract_genre_style
        protagonist_name = resolve_protagonist_name(novel)

        characters_hint = outline_data.get("characters_involved", []) if outline_data else []
        rag_context = await retrieve_setting_context(
            project_id=str(project_id),
            query_text=query_text,
            character_state_txt=character_state,
            world_state_txt=world_state,
            foreshadowing_txt=foreshadowing,
            plot_threads_txt=plot_threads,
            characters_involved_hint=characters_hint,
            protagonist_name=protagonist_name,
            current_chapter=chapter_index,
            foreshadowing_items=all_knowledge.get("foreshadowing", []),
        )

        genre, style = extract_genre_style(novel.outline if novel and novel.outline and isinstance(novel.outline, dict) else None)

        return {
            "previous_ending": previous_ending,
            "intervention": intervention,
            "short_term_context": short_term_context,
            "full_manuscript_context": full_manuscript_context,
            "world_state": rag_context["world_state"],
            "character_state": rag_context["character_state"],
            "foreshadowing": rag_context["foreshadowing"],
            "plot_threads": rag_context["plot_threads"],
            "vector_context": rag_context.get("chapter_extracts", ""),
            "genre": genre,
            "style": style,
            "raw_world_state": world_state,
            "raw_character_state": character_state,
            "raw_foreshadowing": foreshadowing,
            "raw_plot_threads": plot_threads,
            "novel_format": novel.novel_format if novel else "",
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
    ) -> PipelineContext:
        memory = await MemoryManager.get_context(db, project_id, chapter_index, query_text, outline_data)
        return PipelineContext.from_memory(str(project_id), chapter_index, memory)
