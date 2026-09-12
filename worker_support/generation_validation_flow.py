"""Validation execution flow for chapter generation."""

from __future__ import annotations

import json
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
    mark_validator_retry,
    target_word_count_for,
    validation_errors_text,
    validator_retry_message,
    has_fact_conflict,
)
from services.continuity_contract import (
    contract_prompt,
    prompt_outline_for_agent,
    sanitize_outline_for_contract,
)
from worker_support.validation import run_comprehensive_validation, run_quick_validation
from core.pipeline_vocab import ChapterStatus


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
    if mem_context.get("chapter_outline"):
        safe_outline, contract = sanitize_outline_for_contract(
            mem_context["chapter_outline"],
            mem_context.get("chapter_handoff"),
        )
        mem_context["chapter_outline"] = prompt_outline_for_agent(safe_outline)
        mem_context["chapter_contract"] = contract
        mem_context["chapter_contract_context"] = contract_prompt(
            contract, agent_type="validator"
        )
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
    mem_context = await MemoryManager.get_context(db, novel.id, chapter_index, f"第{chapter_index}章", agent_type="validator")
    mem_context["chapter_outline"] = chapter.outline or {}
    mem_context["chapter_outline"], mem_context["chapter_contract"] = sanitize_outline_for_contract(
        mem_context["chapter_outline"],
        mem_context.get("chapter_handoff"),
    )
    mem_context["chapter_outline"] = prompt_outline_for_agent(mem_context["chapter_outline"])
    mem_context["chapter_contract_context"] = contract_prompt(
        mem_context["chapter_contract"], agent_type="validator"
    )
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
            # 终审失败绝不能被自动改写成 passed=True。达到整章重写上限后，
            # 保留失败结论并暂停，等待人工处理；否则 attempt 边会把失败稿
            # 送进 publish，形成“拦截后自动跳过”的假通过。
            validator_result["terminal_block"] = True
            chapter.status = ChapterStatus.DRAFT
            chapter.error = json.dumps(validator_result.get("errors", []), ensure_ascii=False)
            await db.commit()
            await events.status(
                AGENT_VALIDATOR,
                chapter_index,
                (
                    "终审在自动重写 3 次后仍未通过，未强制保存，本章已暂停等待人工处理。"
                    if not has_fact_conflict(validator_result)
                    else "检测到未解决的角色/时间线/设定硬冲突，未强制保存，本章已暂停。"
                ),
            )
            return validator_result

        await events.log(
            STREAM_SOURCE_SYSTEM,
            validator_retry_message(chapter_index, attempt, validator_result["errors"]),
        )
        mark_validator_retry(chapter, validator_result)
        await db.commit()

    return validator_result
