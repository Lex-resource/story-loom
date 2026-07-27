"""Editor execution helpers for chapter generation."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import AGENT_EDITOR, AGENT_VALIDATOR
from worker_support.chapter_repository import get_or_create_chapter, save_editor_raw_issues
from worker_support.events import GenerationEvents
from worker_support.generation_editor_policy import (
    apply_editor_revision,
    editor_edited_content,
    force_save_after_quick_validation_failure,
    mark_editor_rewrite,
    mark_editor_success,
    mark_force_corrected_revision,
    resolve_editor_decision_from_result,
)
from worker_support.generation_validator_policy import (
    apply_cleaned_content,
    validation_errors_text,
)
from worker_support.generation_validation_flow import run_context_comprehensive_validation
from services.validator import analyze_style


@dataclass
class EditorReview:
    chapter: object
    editor_result: dict
    evaluations: dict
    decision: str
    edited_content: str
    raw_issues: list


@dataclass
class PostEditValidationOutcome:
    validator_result: dict
    draft_content: str | None
    edited_content: str | None
    rewrite_count: int
    decision: str
    validation_errors: str
    should_continue: bool


async def run_editor_review(
    db: AsyncSession,
    novel,
    chapter_index: int,
    editor_node,
    pipeline_context,
    draft_content: str | None,
    outline_data: dict,
    issue_summaries: str,
    validation_errors: str,
    rewrite_count: int,
    on_chunk=None,
) -> EditorReview:
    editor_output = await editor_node.run(
        pipeline_context,
        {
            "draft_content": draft_content,
            "chapter_outline": outline_data,
            "issue_summaries": issue_summaries,
            "validation_errors": validation_errors,
            "on_chunk": on_chunk,
        },
    )
    editor_result = editor_output.payload
    await editor_node.agent.record_usage(db, novel.id, chapter_index, AGENT_EDITOR)

    evaluations = editor_result.get("evaluations", {})
    decision = resolve_editor_decision_from_result(editor_result, rewrite_count)
    edited_content = editor_edited_content(editor_result, draft_content)
    raw_issues = editor_result.get("raw_issues", [])

    chapter = await get_or_create_chapter(
        db,
        novel.id,
        chapter_index,
        title=outline_data.get("title", f"第{chapter_index}章"),
        outline=outline_data,
    )

    apply_editor_revision(chapter, draft_content, edited_content, decision, evaluations)

    return EditorReview(
        chapter=chapter,
        editor_result=editor_result,
        evaluations=evaluations,
        decision=decision,
        edited_content=edited_content,
        raw_issues=raw_issues,
    )


async def run_post_edit_validation(
    db: AsyncSession,
    novel,
    chapter_index: int,
    chapter,
    outline_data: dict,
    memory_context: dict,
    draft_content: str | None,
    edited_content: str | None,
    rewrite_count: int,
    max_rewrites: int,
    raw_issues: list,
    events: GenerationEvents,
    validator_agent,
    on_validator_chunk=None,
) -> PostEditValidationOutcome:
    final_text = edited_content or draft_content
    await events.log("校验器", "精修完成，正在对最终正文进行完整设定与逻辑审计…")
    validator_result = await run_context_comprehensive_validation(
        db,
        novel,
        chapter_index,
        chapter.title or outline_data.get("title", f"第{chapter_index}章"),
        final_text,
        memory_context["previous_ending"],
        memory_context,
        validator_agent,
        on_validator_chunk=on_validator_chunk,
    )
    await events.validator_messages(validator_result, chapter_index)
    contents = apply_cleaned_content(validator_result, draft_content, edited_content, chapter)
    draft_content = contents.draft_content
    edited_content = contents.edited_content

    if not validator_result["passed"]:
        rewrite_count += 1
        validation_errors = validation_errors_text(validator_result)
        mark_editor_rewrite(
            chapter,
            rewrite_count,
            "精修稿未通过法则校验",
            f"请修正以下校验问题：\n{validation_errors}",
        )
        await db.commit()
        if rewrite_count >= max_rewrites:
            await events.status(
                AGENT_VALIDATOR,
                chapter_index,
                "内容校验未完全通过，但已达最大重试次数，系统强制保存并继续。",
            )
            force_save_after_quick_validation_failure(chapter)
            await db.commit()
            return PostEditValidationOutcome(
                validator_result=validator_result,
                draft_content=draft_content,
                edited_content=edited_content,
                rewrite_count=rewrite_count,
                decision="rewrite",
                validation_errors=validation_errors,
                should_continue=False,
            )
        return PostEditValidationOutcome(
            validator_result=validator_result,
            draft_content=draft_content,
            edited_content=edited_content,
            rewrite_count=rewrite_count,
            decision="rewrite",
            validation_errors=validation_errors,
            should_continue=True,
        )

    mark_editor_success(chapter, rewrite_count)
    await save_editor_raw_issues(db, novel.id, chapter_index, raw_issues)
    await db.commit()
    return PostEditValidationOutcome(
        validator_result=validator_result,
        draft_content=draft_content,
        edited_content=edited_content,
        rewrite_count=rewrite_count,
        decision="proceed",
        validation_errors="",
        should_continue=False,
    )


@dataclass
class StyleRepairOutcome:
    ran: bool
    edited_content: str | None
    style_report: dict


async def run_style_repair(
    db: AsyncSession,
    novel,
    chapter_index: int,
    chapter,
    editor_node,
    draft_content: str | None,
    edited_content: str | None,
    outline_data: dict,
    memory_context: dict,
    issue_summaries: str,
    events: GenerationEvents,
    on_chunk=None,
) -> StyleRepairOutcome:
    """Detect AI-slop prose and run a style-only repair pass when flagged.

    The detector (services.validator.analyze_style) is a cheap deterministic
    gate, so the expensive LLM destyle call only fires when cliché density or
    rhythm monotony actually crosses threshold. Style repair never changes plot;
    the caller must still re-validate the returned content before publishing.
    """
    final_text = edited_content or draft_content or ""
    style_report = analyze_style(final_text)
    if not style_report["flagged"]:
        return StyleRepairOutcome(ran=False, edited_content=edited_content, style_report=style_report)

    await events.status(
        AGENT_EDITOR,
        chapter_index,
        "检测到 AI 腔/句式单一，正在进行文风精修…",
    )
    editor_result = await editor_node.agent.destyle_chapter(
        final_text,
        outline_data,
        memory_context["world_state"],
        memory_context["character_state"],
        memory_context["foreshadowing"],
        memory_context["previous_ending"],
        issue_summaries,
        style_report=style_report,
        novel_format=novel.novel_format,
        genre=memory_context.get("genre", ""),
        style=memory_context.get("style", ""),
        on_chunk=on_chunk,
    )
    await editor_node.agent.record_usage(db, novel.id, chapter_index, AGENT_EDITOR)

    destyled = editor_edited_content(editor_result, final_text)
    chapter.edited_content = destyled
    chapter.editor_decision = "revise"
    await db.commit()

    return StyleRepairOutcome(ran=True, edited_content=destyled, style_report=style_report)


async def run_force_editor_revision(
    db: AsyncSession,
    novel,
    chapter_index: int,
    chapter,
    editor_node,
    draft_content: str | None,
    outline_data: dict,
    memory_context: dict,
    issue_summaries: str,
    rewrite_reason: str,
    validation_errors: str,
    fallback_evaluations: dict,
    on_chunk=None,
) -> EditorReview:
    editor_result = await editor_node.agent.force_revise_chapter(
        draft_content,
        outline_data,
        memory_context["world_state"],
        memory_context["character_state"],
        memory_context["foreshadowing"],
        memory_context["previous_ending"],
        issue_summaries,
        rewrite_reason=rewrite_reason,
        novel_format=novel.novel_format,
        validation_errors=validation_errors,
        on_chunk=on_chunk,
    )
    await editor_node.agent.record_usage(db, novel.id, chapter_index, AGENT_EDITOR)
    edited_content = editor_edited_content(editor_result, draft_content)
    raw_issues = editor_result.get("raw_issues", [])

    mark_force_corrected_revision(chapter, edited_content, editor_result, fallback_evaluations)

    return EditorReview(
        chapter=chapter,
        editor_result=editor_result,
        evaluations=editor_result.get("evaluations", fallback_evaluations),
        decision="revise",
        edited_content=edited_content,
        raw_issues=raw_issues,
    )
