"""Outline preparation for chapter generation."""

from __future__ import annotations

from agents.constants import AGENT_PLANNER
from agents.pipeline_context import PipelineContext
from sqlalchemy.ext.asyncio import AsyncSession

from worker_support.chapter_repository import (
    load_existing_outline,
    save_planner_outline,
    sync_chapter_outline,
)
from worker_support.events import GenerationEvents
from worker_support.generation_context import append_user_intervention
from services.continuity_contract import sanitize_outline_for_contract

def normalize_outline_data(outline: dict) -> dict:
    """Normalize planner-returned outline dict into a consistent shape."""
    if not isinstance(outline, dict):
        return outline

    key_events = outline.get("key_events", [])
    if not isinstance(key_events, list):
        key_events = [key_events] if key_events else []

    cleaned_key_events = []
    for event in key_events:
        if isinstance(event, dict):
            for key, value in event.items():
                if key not in outline or not outline[key]:
                    outline[key] = value
        elif isinstance(event, str):
            if "emotional_arc" in event and ":" in event:
                try:
                    _, value = event.split(":", 1)
                    if "emotional_arc" not in outline or not outline["emotional_arc"]:
                        outline["emotional_arc"] = value.strip().strip('"').strip("'").strip('\\"')
                except Exception:
                    pass
                continue
            cleaned_key_events.append(event)
        else:
            cleaned_key_events.append(str(event))

    outline["key_events"] = cleaned_key_events

    for list_key in [
        "key_events",
        "required_events",
        "uncertain_events",
        "related_foreshadowing",
        "characters_involved",
        "required_changes",
        "forbidden_changes",
    ]:
        value = outline.get(list_key, [])
        if not isinstance(value, list):
            outline[list_key] = [str(value)] if value else []
        else:
            outline[list_key] = [str(item) for item in value if item]

    character_goals = outline.get("character_goals", [])
    if not isinstance(character_goals, list):
        character_goals = [character_goals] if character_goals else []
    outline["character_goals"] = [
        item for item in character_goals
        if isinstance(item, dict)
    ]

    if "chapter_index" in outline:
        try:
            outline["chapter_index"] = int(outline["chapter_index"])
        except Exception:
            pass

    return outline


async def prepare_chapter_outline(
    db: AsyncSession,
    *,
    novel,
    chapter_index: int,
    use_existing_outline: bool,
    mem_context: dict,
    skeleton: dict,
    issue_summaries: str,
    custom_prompt: str | None,
    planner_node,
    planner_cb,
    planner_previous_ending: str,
    project_id: str,
    events: GenerationEvents,
) -> dict:
    outline_data = None
    if use_existing_outline:
        outline_data = await load_existing_outline(db, novel.id, chapter_index)
        if outline_data:
            outline_data = normalize_outline_data(outline_data)
            outline_data, contract = sanitize_outline_for_contract(
                outline_data,
                mem_context.get("chapter_handoff"),
            )
            outline_data["continuity_contract"] = contract
            await events.status(AGENT_PLANNER, chapter_index, "使用已有大纲进行重写...")

    if not outline_data:
        await events.status(
            AGENT_PLANNER,
            chapter_index,
            f"策划智能体正在生成第 {chapter_index} 章大纲...",
        )
        extended_previous_ending = planner_previous_ending
        planner_context = PipelineContext.from_memory(
            project_id,
            chapter_index,
            {
                **mem_context,
                "previous_ending": extended_previous_ending,
                "global_outline": skeleton,
                "intervention": append_user_intervention(
                    custom_prompt,
                    mem_context.get("intervention"),
                ),
            },
        )
        planner_output = await planner_node.run(
            planner_context,
            {"skeleton": skeleton, "issue_summaries": issue_summaries, "on_chunk": planner_cb},
        )
        outline_data = normalize_outline_data(planner_output.payload["chapter_outline"])
        outline_data, contract = sanitize_outline_for_contract(
            outline_data,
            mem_context.get("chapter_handoff"),
        )
        outline_data["continuity_contract"] = contract
        await planner_node.agent.record_usage(db, novel.id, chapter_index, AGENT_PLANNER)

        await save_planner_outline(db, novel.id, chapter_index, outline_data)
        await db.commit()

    await sync_chapter_outline(db, novel.id, chapter_index, outline_data)
    await db.commit()

    return outline_data
