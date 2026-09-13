"""Planner preparation helpers for chapter generation."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from worker_support.chapter_repository import get_succeeding_chapter_beginning
from worker_support.context import MemoryManager
from worker_support.generation_context import (
    append_succeeding_beginning_warning,
    load_issue_summaries,
)


@dataclass
class PlannerPreparation:
    memory: dict
    custom_prompt: str | None
    succeeding_beginning: str
    previous_ending: str
    issue_summaries: str


async def prepare_planner_inputs(
    db: AsyncSession,
    novel,
    chapter_index: int,
    custom_prompt: str | None,
    domain: ChapterDomain | None = None,
    previous_ending_override: str | None = None,
) -> PlannerPreparation:
    planner_query = f"第{chapter_index}章"
    memory = await MemoryManager.get_context(
        db,
        novel.id,
        chapter_index,
        planner_query,
        agent_type="planner",
        branch_id=domain.branch_id if domain else None,
        storyline_id=domain.storyline_id if domain else "main",
        previous_ending_override=previous_ending_override,
    )
    succeeding_beginning = await get_succeeding_chapter_beginning(
        db,
        novel.id,
        chapter_index,
        max_chars=1500,
        domain=domain,
    )
    previous_ending = append_succeeding_beginning_warning(
        memory["previous_ending"],
        succeeding_beginning,
        chapter_index,
    )
    issue_summaries = await load_issue_summaries(db, novel.id)
    return PlannerPreparation(
        memory=memory,
        custom_prompt=custom_prompt,
        succeeding_beginning=succeeding_beginning,
        previous_ending=previous_ending,
        issue_summaries=issue_summaries,
    )
