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
    mark_editor_rewrite,
    mark_editor_success,
    mark_force_corrected_revision,
    resolve_editor_decision_from_result,
)
from worker_support.generation_validator_policy import (
    apply_cleaned_content,
    has_fact_conflict,
    validation_errors_text,
)
from services.version_surface import NO_OVERRIDE, research_override
from worker_support.generation_validation_flow import run_context_comprehensive_validation
from services.validator import analyze_style
from services.experiment_recorder import record_event
from services.continuity_contract import prompt_outline_for_agent
from services.quality_metrics import quality_summary


def _polisher_gate(validator_result: dict) -> dict:
    """A5 额外 Editor 调用的门控。生产（A28）不启用，恒返回不合格。"""
    gate = research_override("polisher_gate", validator_result)
    if gate is NO_OVERRIDE:
        return {"enabled": False, "eligible": False, "reason": "production_a28", "issue_count": 0}
    return gate


def _record_quality_role(role: str, **fields) -> None:
    """记录 A5/A6/A7 质量角色事件。生产下是空操作。"""
    research_override("quality_role_event", role, **fields)


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
    a5_polisher_used: bool


async def _run_a5_polisher(
    db: AsyncSession,
    novel,
    chapter_index: int,
    chapter,
    editor_node,
    outline_data: dict,
    memory_context: dict,
    draft_content: str | None,
    edited_content: str | None,
    issue_summaries: str,
    validator_result: dict,
    on_chunk=None,
) -> str:
    """Apply one evidence-backed local repair before spending a Writer retry."""
    final_text = edited_content or draft_content or ""
    errors = validation_errors_text(validator_result)
    _record_quality_role(
        "polisher",
        action="start",
        categories=sorted(
            {
                str(issue.get("category") or "")
                for issue in validator_result.get("hard_issues", []) or []
                if isinstance(issue, dict)
            }
        ),
    )
    editor_result = await editor_node.agent.force_revise_chapter(
        final_text,
        prompt_outline_for_agent(outline_data),
        memory_context.get("world_state", ""),
        memory_context.get("character_state", ""),
        memory_context.get("foreshadowing", ""),
        memory_context.get("previous_ending", ""),
        issue_summaries,
        rewrite_reason="A5 硬连续性问题定点修复",
        novel_format=novel.novel_format,
        validation_errors=errors,
        genre=memory_context.get("genre", ""),
        style=memory_context.get("style", ""),
        on_chunk=on_chunk,
    )
    repaired = editor_edited_content(editor_result, final_text)
    chapter.edited_content = repaired
    chapter.editor_decision = "revise"
    await editor_node.agent.record_usage(db, novel.id, chapter_index, AGENT_EDITOR)
    await db.commit()
    _record_quality_role("polisher", action="completed", output_chars=len(repaired))
    return repaired


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
            "chapter_outline": prompt_outline_for_agent(outline_data),
            "issue_summaries": issue_summaries,
            "validation_errors": validation_errors,
            "on_chunk": on_chunk,
        },
    )
    editor_result = editor_output.payload
    await editor_node.agent.record_usage(db, novel.id, chapter_index, AGENT_EDITOR)

    evaluations = editor_result.get("evaluations", {})
    record_event("quality_evaluation", quality_summary(evaluations, novel.novel_format))
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


async def _run_v49_local_observation_repair(
    db: AsyncSession,
    novel,
    chapter_index: int,
    chapter,
    editor_node,
    outline_data: dict,
    memory_context: dict,
    edited_content: str,
    validator_result: dict,
    repair_plan: dict,
    on_editor_chunk=None,
) -> str:
    """Repair observation-language overreach without asking Writer to restart."""
    errors = repair_plan.get("contract") or validation_errors_text(validator_result)
    repair_type = repair_plan.get("repair_type") or "observation_language_boundary"
    record_event(
        "local_editor_repair",
        {
            "repair_type": repair_type,
            "issue_count": len(validator_result.get("hard_issues", []) or []),
        },
    )
    editor_result = await editor_node.agent.force_revise_chapter(
        edited_content,
        prompt_outline_for_agent(outline_data),
        memory_context.get("world_state", ""),
        memory_context.get("character_state", ""),
        memory_context.get("foreshadowing", ""),
        memory_context.get("previous_ending", ""),
        "",
        rewrite_reason=repair_plan.get("rewrite_reason") or "观察语言局部修复",
        novel_format=novel.novel_format,
        validation_errors=errors,
        genre=memory_context.get("genre", ""),
        style=memory_context.get("style", ""),
        on_chunk=on_editor_chunk,
    )
    repaired = editor_edited_content(editor_result, edited_content)
    chapter.edited_content = repaired
    chapter.editor_decision = "revise"
    await editor_node.agent.record_usage(db, novel.id, chapter_index, AGENT_EDITOR)
    await db.commit()
    return repaired


async def _run_v54_local_action_repair(
    db: AsyncSession,
    novel,
    chapter_index: int,
    chapter,
    editor_node,
    outline_data: dict,
    memory_context: dict,
    edited_content: str,
    validator_result: dict,
    repair_plan: dict,
    on_editor_chunk=None,
) -> str:
    """Repair duplicate operations and unknown labels without Writer restart."""
    record_event(
        "local_editor_repair",
        {
            "repair_type": "intra_chapter_action_surface",
            "issue_count": len(validator_result.get("hard_issues", []) or []),
        },
    )
    editor_result = await editor_node.agent.force_revise_chapter(
        edited_content,
        prompt_outline_for_agent(outline_data),
        memory_context.get("world_state", ""),
        memory_context.get("character_state", ""),
        memory_context.get("foreshadowing", ""),
        memory_context.get("previous_ending", ""),
        "",
        rewrite_reason="V54 章节内动作局部修复",
        novel_format=novel.novel_format,
        validation_errors=repair_plan.get("contract") or validation_errors_text(validator_result),
        genre=memory_context.get("genre", ""),
        style=memory_context.get("style", ""),
        on_chunk=on_editor_chunk,
    )
    repaired = editor_edited_content(editor_result, edited_content)
    chapter.edited_content = repaired
    chapter.editor_decision = "revise"
    await editor_node.agent.record_usage(db, novel.id, chapter_index, AGENT_EDITOR)
    await db.commit()
    return repaired


async def _revalidate_repaired(
    db: AsyncSession,
    novel,
    chapter_index: int,
    chapter,
    outline_data: dict,
    memory_context: dict,
    repaired: str,
    validator_agent,
    on_validator_chunk,
    events: GenerationEvents,
) -> dict:
    """局部修复后的复核校验:完整 validator 重跑 + 前端消息。"""
    repaired_result = await run_context_comprehensive_validation(
        db,
        novel,
        chapter_index,
        chapter.title or outline_data.get("title", f"第{chapter_index}章"),
        repaired,
        memory_context["previous_ending"],
        memory_context,
        validator_agent,
        on_validator_chunk=on_validator_chunk,
    )
    await events.validator_messages(repaired_result, chapter_index)
    return repaired_result


def _accepted_outcome(
    repaired_result: dict,
    draft_content: str | None,
    repaired: str | None,
    rewrite_count: int,
    a5_polisher_used: bool,
) -> PostEditValidationOutcome:
    return PostEditValidationOutcome(
        validator_result=repaired_result,
        draft_content=draft_content,
        edited_content=repaired,
        rewrite_count=rewrite_count,
        decision="proceed",
        validation_errors="",
        should_continue=False,
        a5_polisher_used=a5_polisher_used,
    )


async def _commit_accepted_repair(
    db: AsyncSession,
    novel,
    chapter_index: int,
    chapter,
    rewrite_count: int,
    raw_issues: list,
) -> None:
    """修复稿通过复核后的收尾:标记成功、留档 issue、提交。"""
    mark_editor_success(chapter, rewrite_count)
    await save_editor_raw_issues(db, novel.id, chapter_index, raw_issues)
    await db.commit()


async def _terminal_block_outcome(
    db: AsyncSession,
    novel,
    chapter_index: int,
    chapter,
    events: GenerationEvents,
    validator_result: dict,
    validation_errors: str,
    rewrite_count: int,
    draft_content: str | None,
    edited_content: str | None,
    a5_polisher_used: bool,
    reason: str,
) -> PostEditValidationOutcome:
    """重写预算耗尽后的停机:置 terminal_block、暂停章节,不强制发布。"""
    validator_result["terminal_block"] = True
    chapter.status = "draft"
    chapter.error = validation_errors
    await db.commit()
    await events.status(AGENT_VALIDATOR, chapter_index, reason)
    return PostEditValidationOutcome(
        validator_result=validator_result,
        draft_content=draft_content,
        edited_content=edited_content,
        rewrite_count=rewrite_count,
        decision="blocked",
        validation_errors=validation_errors,
        should_continue=False,
        a5_polisher_used=a5_polisher_used,
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
    on_editor_chunk=None,
    editor_node=None,
    a5_polisher_used: bool = False,
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
        # 是否走 Editor 局部修复由研究覆盖层决定。A28/V43 生产不做这类修复
        # （对应的 issue 分类整段起于 V49，高于冻结点），因此 plan 恒为 None。
        repair_plan = research_override("local_repair_plan", validator_result)
        if repair_plan is NO_OVERRIDE:
            repair_plan = None
        if (
            repair_plan
            and repair_plan.get("kind") == "observation"
            and editor_node is not None
        ):
            repaired = await _run_v49_local_observation_repair(
                db,
                novel,
                chapter_index,
                chapter,
                editor_node,
                outline_data,
                memory_context,
                edited_content or draft_content or "",
                validator_result,
                repair_plan,
                on_editor_chunk=on_editor_chunk,
            )
            repaired_result = await _revalidate_repaired(
                db, novel, chapter_index, chapter, outline_data, memory_context,
                repaired, validator_agent, on_validator_chunk, events,
            )
            if repaired_result.get("passed"):
                await _commit_accepted_repair(db, novel, chapter_index, chapter, rewrite_count, raw_issues)
                return _accepted_outcome(repaired_result, draft_content, repaired, rewrite_count, a5_polisher_used)
            validator_result = repaired_result
            contents = apply_cleaned_content(
                repaired_result,
                draft_content,
                repaired,
                chapter,
            )
            draft_content = contents.draft_content
            edited_content = contents.edited_content

        action_plan = research_override("local_repair_plan", validator_result)
        if action_plan is NO_OVERRIDE:
            action_plan = None
        if (
            action_plan
            and action_plan.get("kind") == "action_surface"
            and editor_node is not None
        ):
            repaired = await _run_v54_local_action_repair(
                db,
                novel,
                chapter_index,
                chapter,
                editor_node,
                outline_data,
                memory_context,
                edited_content or draft_content or "",
                validator_result,
                action_plan,
                on_editor_chunk=on_editor_chunk,
            )
            repaired_result = await _revalidate_repaired(
                db, novel, chapter_index, chapter, outline_data, memory_context,
                repaired, validator_agent, on_validator_chunk, events,
            )
            if repaired_result.get("passed"):
                await _commit_accepted_repair(db, novel, chapter_index, chapter, rewrite_count, raw_issues)
                return _accepted_outcome(repaired_result, draft_content, repaired, rewrite_count, a5_polisher_used)
            validator_result = repaired_result
            contents = apply_cleaned_content(
                repaired_result,
                draft_content,
                repaired,
                chapter,
            )
            draft_content = contents.draft_content
            edited_content = contents.edited_content

        gate = _polisher_gate(validator_result)
        if gate["eligible"] and not a5_polisher_used and editor_node is not None:
            _record_quality_role("detail", action="hard_issue_context_attached")
            repaired = await _run_a5_polisher(
                db,
                novel,
                chapter_index,
                chapter,
                editor_node,
                outline_data,
                memory_context,
                draft_content,
                edited_content,
                memory_context.get("issue_summaries", ""),
                validator_result,
                on_chunk=on_editor_chunk,
            )
            repaired_result = await _revalidate_repaired(
                db, novel, chapter_index, chapter, outline_data, memory_context,
                repaired, validator_agent, on_validator_chunk, events,
            )
            _record_quality_role(
                "critic",
                action="recheck_polished_content",
                passed=bool(repaired_result.get("passed")),
            )
            if repaired_result.get("passed"):
                await _commit_accepted_repair(db, novel, chapter_index, chapter, rewrite_count, raw_issues)
                return _accepted_outcome(repaired_result, draft_content, repaired, rewrite_count, a5_polisher_used=True)
            a5_polisher_used = True
            validator_result = repaired_result
            contents = apply_cleaned_content(
                repaired_result,
                draft_content,
                repaired,
                chapter,
            )
            draft_content = contents.draft_content
            edited_content = contents.edited_content

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
            if has_fact_conflict(validator_result):
                return await _terminal_block_outcome(
                    db, novel, chapter_index, chapter, events,
                    validator_result, validation_errors, rewrite_count,
                    draft_content, edited_content, a5_polisher_used,
                    reason="最终校验仍发现角色/时间线/设定硬冲突，本章已暂停，未强制发布。",
                )
            return await _terminal_block_outcome(
                db, novel, chapter_index, chapter, events,
                validator_result, validation_errors, rewrite_count,
                draft_content, edited_content, a5_polisher_used,
                reason="编辑后法则校验在自动重写次数耗尽后仍未通过，未强制保存，本章已暂停等待人工处理。",
            )
        return PostEditValidationOutcome(
            validator_result=validator_result,
            draft_content=draft_content,
            edited_content=edited_content,
            rewrite_count=rewrite_count,
            decision="rewrite",
            validation_errors=validation_errors,
            should_continue=True,
            a5_polisher_used=a5_polisher_used,
        )

    mark_editor_success(chapter, rewrite_count)
    await save_editor_raw_issues(db, novel.id, chapter_index, raw_issues)
    await db.commit()
    return _accepted_outcome(
        validator_result, draft_content, edited_content, rewrite_count, a5_polisher_used,
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
    force: bool = False,
) -> StyleRepairOutcome:
    """Detect AI-slop prose and run a style-only repair pass when flagged.

    The detector (services.validator.analyze_style) is a cheap deterministic
    gate, so the expensive LLM destyle call only fires when cliché density or
    rhythm monotony actually crosses threshold. Style repair never changes plot;
    the caller must still re-validate the returned content before publishing.

    ``force=True`` 绕过门控。自定义润色节点（口语化重写、节奏加速之类）想无条件跑一遍，
    而内置的去 AI 腔要保持只在检测到问题时才烧 token —— 见
    ``worker_support/chapter_steps.run_style_repair_step``。
    """
    final_text = edited_content or draft_content or ""
    style_report = analyze_style(final_text)
    if not style_report["flagged"] and not force:
        return StyleRepairOutcome(ran=False, edited_content=edited_content, style_report=style_report)

    await events.status(
        AGENT_EDITOR,
        chapter_index,
        "检测到 AI 腔/句式单一，正在进行文风精修…",
    )
    editor_result = await editor_node.agent.destyle_chapter(
        final_text,
        prompt_outline_for_agent(outline_data),
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
        prompt_outline_for_agent(outline_data),
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
