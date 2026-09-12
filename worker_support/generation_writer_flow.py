"""Writer execution helpers for chapter generation."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import (
    AGENT_WRITER,
    KEY_CHAPTER_CANDIDATE_COUNT,
    KEY_CHAPTER_STAGES,
)
from agents.pipeline_context import PipelineContext
from services.validator import style_quality_score
from worker_support.chapter_repository import get_chapter_by_index
from worker_support.context import MemoryManager
from worker_support.generation_context import writer_query_from_outline
from worker_support.generation_validator_policy import target_word_count_for
from services.character_context import build_writer_character_context
from services.chapter_continuity import writer_execution_brief
from services.context_compaction import context_budget_for
from services.continuity_contract import (
    contract_prompt,
    prompt_outline_for_agent,
    sanitize_outline_for_contract,
)
from services.novel_memory_recall import remove_authority_duplicates


@dataclass
class WriterContext:
    memory: dict
    pipeline: PipelineContext


async def load_writer_context(
    db: AsyncSession,
    novel,
    chapter_index: int,
    outline_data: dict,
) -> WriterContext:
    writer_query = writer_query_from_outline(outline_data)
    memory = await MemoryManager.get_context(
        db,
        novel.id,
        chapter_index,
        writer_query,
        outline_data,
        agent_type="writer",
    )
    memory["character_card_context"] = await build_writer_character_context(
        db,
        novel.id,
        chapter_index,
        outline_data.get("characters_involved", []),
    )
    memory["novel_memory_context"] = remove_authority_duplicates(
        memory.get("character_card_context", ""),
        memory.get("novel_memory_context", ""),
        context_budget_for("writer").memory_chars,
    )
    outline_data, memory["chapter_contract"] = sanitize_outline_for_contract(
        outline_data,
        memory.get("chapter_handoff"),
    )
    memory["chapter_outline"] = prompt_outline_for_agent(
        outline_data, agent_type="writer"
    )
    memory["chapter_contract_context"] = contract_prompt(
        memory["chapter_contract"], agent_type="writer"
    )
    memory["writer_execution_brief_context"] = writer_execution_brief(
        memory.get("chapter_handoff"),
        memory.get("chapter_contract"),
        novel_format=novel.novel_format,
        outline=outline_data,
    )
    memory.setdefault("context_sources", {})["writer_execution_brief_context"] = {
        "source_ref": f"chapter:{chapter_index}:writer-execution-brief",
        "source_chapter": chapter_index,
        "authority": "accepted_projection",
    }
    memory["chapter_handoff_context"] = ""
    memory["chapter_contract_context"] = ""
    pipeline = PipelineContext.from_memory(str(novel.id), chapter_index, memory)
    return WriterContext(memory=memory, pipeline=pipeline)


def prepare_writer_pipeline_context(
    pipeline_context: PipelineContext,
    skeleton: dict,
    outline_data: dict,
) -> PipelineContext:
    outline_data, contract = sanitize_outline_for_contract(
        outline_data,
        pipeline_context.chapter_handoff,
    )
    pipeline_context.global_outline = skeleton
    pipeline_context.chapter_outline = prompt_outline_for_agent(
        outline_data, agent_type="writer"
    )
    pipeline_context.chapter_contract = contract
    pipeline_context.chapter_contract_context = contract_prompt(
        contract, agent_type="writer"
    )
    pipeline_context.writer_execution_brief_context = writer_execution_brief(
        pipeline_context.chapter_handoff,
        contract,
        novel_format=pipeline_context.novel_format,
        outline=outline_data,
    )
    pipeline_context.chapter_handoff_context = ""
    pipeline_context.chapter_contract_context = ""
    return pipeline_context


def is_key_chapter(outline_data: dict) -> bool:
    """A high-tension chapter worth spending extra candidates on."""
    stage = (outline_data or {}).get("narrative_stage", "")
    return stage in KEY_CHAPTER_STAGES


def candidate_count_for(outline_data: dict) -> int:
    """How many drafts to generate: N for key chapters, 1 otherwise."""
    if is_key_chapter(outline_data):
        return max(1, KEY_CHAPTER_CANDIDATE_COUNT)
    return 1


def select_best_candidate(candidates: list[str]) -> str:
    """Pick the best-reading draft by the deterministic style scorer.

    Ties (and the single-candidate case) keep the first draft, so behaviour is
    unchanged when only one candidate is generated.
    """
    best = candidates[0]
    best_score = style_quality_score(best)
    for candidate in candidates[1:]:
        score = style_quality_score(candidate)
        if score > best_score:
            best, best_score = candidate, score
    return best


async def run_writer_draft(
    db: AsyncSession,
    novel,
    chapter_index: int,
    writer_node,
    pipeline_context: PipelineContext,
    outline_data: dict,
    skeleton: dict,
    issue_summaries: str,
    rewrite_instructions: str,
    on_chunk=None,
) -> str:
    prepared_context = prepare_writer_pipeline_context(pipeline_context, skeleton, outline_data)
    inputs = {
        "chapter_outline": prepared_context.chapter_outline,
        "skeleton": skeleton,
        "issue_summaries": issue_summaries,
        "word_count": target_word_count_for(novel),
        "rewrite_instructions": rewrite_instructions,
        "on_chunk": on_chunk,
    }

    num_candidates = candidate_count_for(outline_data)
    candidates = []
    for i in range(num_candidates):
        # Only the first candidate streams to the UI; extra candidates run silent
        # so the reader isn't shown drafts that may be discarded.
        candidate_inputs = inputs if i == 0 else {**inputs, "on_chunk": None}
        writer_output = await writer_node.run(prepared_context, candidate_inputs)
        await writer_node.agent.record_usage(db, novel.id, chapter_index, AGENT_WRITER)
        candidates.append(writer_output.content)

    return select_best_candidate(candidates)


async def save_writer_draft(
    db: AsyncSession,
    novel,
    chapter_index: int,
    draft_content: str,
):
    chapter = await get_chapter_by_index(db, novel.id, chapter_index)
    if chapter:
        chapter.draft_content = draft_content
        await db.commit()
    return chapter
