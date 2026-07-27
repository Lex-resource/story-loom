"""Validation execution flow for chapter generation."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import AGENT_VALIDATOR
from services.stream_constants import STREAM_SOURCE_SYSTEM
from worker_support.context import MemoryManager
from worker_support.events import GenerationEvents
from worker_support.generation_editor_policy import mark_editor_skipped
from worker_support.generation_validator_policy import (
    apply_cleaned_content,
    apply_cleaned_validator_fields,
    force_save_validator_result,
    mark_validator_retry,
    target_word_count_for,
    validation_errors_text,
    validator_force_save_message,
    validator_retry_message,
)
from worker_support.validation import run_comprehensive_validation, run_quick_validation


async def run_context_comprehensive_validation(
    db: AsyncSession,
    novel,
    chapter_index: int,
    title: str,
    content: str,
    previous_ending: str,
    mem_context: dict[str, Any],
    validator_agent,
    on_validator_chunk=None,
) -> dict[str, Any]:
    return await run_comprehensive_validation(
        db,
        novel.id,
        chapter_index,
        title,
        content,
        target_word_count_for(novel),
        previous_ending,
        mem_context,
        validator_agent,
        on_validator_chunk=on_validator_chunk,
    )


async def run_context_quick_validation(
    db: AsyncSession,
    novel,
    chapter_index: int,
    title: str,
    content: str,
    previous_ending: str,
    mem_context: dict[str, Any],
) -> dict[str, Any]:
    return await run_quick_validation(
        db,
        novel.id,
        chapter_index,
        title,
        content,
        target_word_count_for(novel),
        previous_ending,
        mem_context,
    )


async def run_pre_editor_validation(
    db: AsyncSession,
    novel,
    chapter_index: int,
    title: str,
    draft_content: str | None,
    edited_content: str | None,
    previous_ending: str,
    mem_context: dict[str, Any],
    chapter,
    validator_agent,
    events: GenerationEvents,
    *,
    has_editor: bool,
    on_validator_chunk=None,
) -> dict[str, Any]:
    current_text = edited_content or draft_content or ""
    if has_editor:
        validator_result = await run_context_quick_validation(
            db,
            novel,
            chapter_index,
            title,
            current_text,
            previous_ending,
            mem_context,
        )
    else:
        validator_result = await run_context_comprehensive_validation(
            db,
            novel,
            chapter_index,
            title,
            current_text,
            previous_ending,
            mem_context,
            validator_agent,
            on_validator_chunk=on_validator_chunk,
        )
    await events.validator_messages(validator_result, chapter_index)
    contents = apply_cleaned_content(validator_result, draft_content, edited_content, chapter)
    validation_errors = validation_errors_text(validator_result)

    if not has_editor and chapter:
        mark_editor_skipped(
            chapter,
            contents.draft_content,
            contents.edited_content,
            validator_result,
        )
        await db.commit()

    return {
        "validator_result": validator_result,
        "draft_content": contents.draft_content,
        "edited_content": contents.edited_content,
        "current_text": contents.current_text,
        "validation_errors": validation_errors,
    }


async def run_saved_chapter_comprehensive_validation(
    db: AsyncSession,
    novel,
    chapter,
    chapter_index: int,
    validator_agent,
    on_validator_chunk=None,
) -> dict[str, Any]:
    mem_context = await MemoryManager.get_context(db, novel.id, chapter_index, f"第{chapter_index}章")
    return await run_context_comprehensive_validation(
        db,
        novel,
        chapter_index,
        chapter.title or "",
        chapter.edited_content or chapter.draft_content or "",
        mem_context["previous_ending"],
        mem_context,
        validator_agent,
        on_validator_chunk=on_validator_chunk,
    )


async def run_final_validator_flow(
    db: AsyncSession,
    novel,
    chapter,
    chapter_index: int,
    attempt: int,
    validator_result: dict[str, Any],
    validator_agent,
    events: GenerationEvents,
    on_validator_chunk=None,
) -> dict[str, Any]:
    await events.validator_messages(validator_result, chapter_index)
    apply_cleaned_validator_fields(validator_result, chapter)
    chapter.validator_result = validator_result

    if not validator_result["passed"]:
        if attempt >= 3:
            force_save_validator_result(chapter, validator_result)
            await db.commit()
            await events.status(
                AGENT_VALIDATOR,
                chapter_index,
                validator_force_save_message(validator_result.get("errors", [])),
            )
            return chapter.validator_result

        await events.log(
            STREAM_SOURCE_SYSTEM,
            validator_retry_message(chapter_index, attempt, validator_result["errors"]),
        )
        mark_validator_retry(chapter, validator_result)
        await db.commit()

    return validator_result
