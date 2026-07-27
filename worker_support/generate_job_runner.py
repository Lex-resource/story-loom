"""章节生成流程主逻辑：单章生成 + 批量调度。

本模块由 worker_support/orchestrator.py 调度。orchestrator 负责 Job 轮询、并发槽位、
状态流转封装；本模块负责单章 planner -> writer -> editor -> validator -> extractor
的流水线执行，以及批量 generate 任务的循环。

异常类 JobAbortedException / JobPausedException 由 generation_exceptions 定义，被
orchestrator.check_paused 抛出，由单章/批量流程捕获处理。
"""
from __future__ import annotations

import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import (
    AGENT_EDITOR,
    AGENT_VALIDATOR,
    AGENT_WRITER,
)
from models.novel import (
    Job,
)
from services.job_payload import (
    get_job_params,
)
from services.pipeline_transitions import (
    StateMachine,
    set_job_step,
)
from services.pipeline_types import ChapterStatus
from worker_support.generation_context import (
    append_user_intervention,
    rewrite_instructions_for_writer,
)
from worker_support.chapter_repository import (
    get_chapter_by_index,
    prepare_chapter_for_step,
)
from worker_support.events import GenerationEvents
from worker_support.generation_exceptions import JobAbortedException, JobPausedException
from worker_support.generation_nodes import editor, planner, validator_agent, writer
from worker_support.generation_outline import prepare_chapter_outline
from worker_support.generation_postprocess import run_chapter_post_processing
from worker_support.generation_editor_policy import mark_editor_rewrite
from worker_support.generation_start_policy import (
    initial_generation_loop_state,
    resolve_generation_start_state,
)
from worker_support.generation_validator_policy import finalize_validated_chapter
from worker_support.pipeline_runtime import load_generation_pipeline_runtime
from worker_support.generation_planner_flow import prepare_planner_inputs
from worker_support.generation_validation_flow import (
    run_final_validator_flow,
    run_pre_editor_validation,
    run_saved_chapter_comprehensive_validation,
)
from worker_support.generation_writer_flow import (
    load_writer_context,
    run_writer_draft,
    save_writer_draft,
)
from worker_support.generation_editor_flow import (
    run_editor_review,
    run_force_editor_revision,
    run_post_edit_validation,
    run_style_repair,
)


# ---------------------------------------------------------------------------
# Single chapter pipeline
# ---------------------------------------------------------------------------

async def process_single_chapter(
    db: AsyncSession, job: Job, novel, next_chapter: int, attempt: int = 1
):
    """Run planner -> writer -> editor -> validator -> extractor for one chapter.

    Raises JobPausedException / JobAbortedException if status changed mid-run
    (via check_paused checks scattered throughout).
    """
    # Lazy import to avoid orchestrator <-> generate_job_runner circular import.
    from worker_support.orchestrator import check_paused

    runtime = await load_generation_pipeline_runtime(db, novel.novel_format)

    await check_paused(db, job.id)
    job.current_chapter = next_chapter

    chapter = await get_chapter_by_index(db, novel.id, next_chapter)
    if chapter and chapter.status == ChapterStatus.PENDING_REVIEW:
        job.current_step = chapter.pipeline_step or job.current_step or "extractor"
        StateMachine.pause_job(job, novel=novel)
        await db.commit()
        return

    start_state = resolve_generation_start_state(
        job,
        chapter,
        get_job_params(job),
        has_editor=runtime.has_editor,
    )
    start_step = start_state.start_step
    set_job_step(job, start_step, chapter, allow_resume=True)

    use_existing_outline = start_state.use_existing_outline
    custom_prompt = start_state.custom_prompt

    chapter = await prepare_chapter_for_step(db, chapter, novel.id, next_chapter, start_step)

    await db.commit()
    project_id_str = str(novel.id)
    events = GenerationEvents(project_id_str)

    async def planner_cb(channel: str, chunk: str):
        if channel != "llm":
            return
        await events.chunk("planner", next_chapter, chunk)

    async def writer_cb(channel: str, chunk: str):
        if channel != "llm":
            return
        await events.chunk("writer", next_chapter, chunk)

    async def editor_cb(channel: str, chunk: str):
        if channel != "llm":
            return
        await events.chunk("editor", next_chapter, chunk)

    async def validator_cb(phase: str, text: str):
        if phase != "llm":
            return
        await events.chunk("validator", next_chapter, text, phase=phase)

    skeleton = novel.outline or {}

    await check_paused(db, job.id)

    planner_inputs = await prepare_planner_inputs(db, novel, next_chapter, custom_prompt)
    mem_context = planner_inputs.memory
    custom_prompt = planner_inputs.custom_prompt
    succeeding_beginning = planner_inputs.succeeding_beginning
    issue_summaries = planner_inputs.issue_summaries

    outline_data = await prepare_chapter_outline(
        db,
        novel=novel,
        chapter_index=next_chapter,
        use_existing_outline=use_existing_outline,
        mem_context=mem_context,
        skeleton=skeleton,
        issue_summaries=issue_summaries,
        planner_node=planner,
        planner_cb=planner_cb,
        planner_previous_ending=planner_inputs.previous_ending,
        project_id=project_id_str,
        events=events,
    )

    if not outline_data or not outline_data.get("summary"):
        await events.error(f"第 {next_chapter} 章大纲为空或生成失败，已暂停生成，请手动补充。")
        # Keep current_step = "planner" so resume re-runs the planner.
        job.current_step = "planner"
        StateMachine.pause_job(job)
        await db.commit()
        return

    # Auto-approve the outline and transition to writer
    if start_step == "planner":
        set_job_step(job, "writer", chapter)
        await db.commit()

    loop_state = initial_generation_loop_state(
        chapter,
        start_step,
        max_rewrites=runtime.max_rewrites,
    )
    draft_content = loop_state.draft_content
    edited_content = loop_state.edited_content
    rewrite_count = loop_state.rewrite_count
    max_rewrites = loop_state.max_rewrites
    decision = loop_state.decision
    validation_errors_str = loop_state.validation_errors
    latest_validator_result = loop_state.latest_validator_result
    raw_issues = loop_state.raw_issues

    if not loop_state.skip_write_edit:
        await check_paused(db, job.id)
        if start_step == "editor" and draft_content and runtime.has_editor:
            set_job_step(job, "editor", chapter, allow_resume=True)
        else:
            set_job_step(job, "writer", chapter, allow_resume=True)
        await db.commit()

    while rewrite_count < max_rewrites:
        writer_context = await load_writer_context(db, novel, next_chapter, outline_data)
        mem_context = writer_context.memory
        pipeline_context = writer_context.pipeline

        if decision == "rewrite":
            custom_prompt = append_user_intervention(custom_prompt, pipeline_context.intervention)

            prev_ch = await get_chapter_by_index(db, novel.id, next_chapter)
            rewrite_instructions = rewrite_instructions_for_writer(
                custom_prompt,
                prev_ch.error if prev_ch else None,
                succeeding_beginning,
                next_chapter,
            )

            await check_paused(db, job.id)
            set_job_step(job, "writer", chapter, allow_resume=True)
            await db.commit()
            await events.status(
                AGENT_WRITER,
                next_chapter,
                (
                    f"作家智能体正在创作初稿... (第 {rewrite_count + 1} 次尝试)"
                    if rewrite_count > 0 else "作家智能体正在创作初稿..."
                ),
            )

            draft_content = await run_writer_draft(
                db,
                novel,
                next_chapter,
                writer,
                pipeline_context,
                outline_data,
                skeleton,
                issue_summaries,
                rewrite_instructions,
                on_chunk=writer_cb,
            )
            edited_content = None
            chapter = await save_writer_draft(db, novel, next_chapter, draft_content)

        if runtime.validation_before_editor:
            pre_editor_validation = await run_pre_editor_validation(
                db,
                novel,
                next_chapter,
                outline_data.get("title", f"第{next_chapter}章"),
                draft_content,
                edited_content,
                pipeline_context.previous_ending,
                mem_context,
                chapter,
                validator_agent,
                events,
                has_editor=runtime.has_editor,
                on_validator_chunk=validator_cb,
            )
            latest_validator_result = pre_editor_validation["validator_result"]
            draft_content = pre_editor_validation["draft_content"]
            edited_content = pre_editor_validation["edited_content"]
            validation_errors_str = pre_editor_validation["validation_errors"]
        else:
            latest_validator_result = None
            validation_errors_str = ""

        if not runtime.has_editor:
            break

        await check_paused(db, job.id)
        set_job_step(job, "editor", chapter)
        await db.commit()
        await events.status(AGENT_EDITOR, next_chapter, "编辑智能体正在审阅及润色文稿...")
        editor_review = await run_editor_review(
            db,
            novel,
            next_chapter,
            editor,
            pipeline_context,
            draft_content,
            outline_data,
            issue_summaries,
            validation_errors_str,
            rewrite_count,
            on_chunk=editor_cb,
        )
        chapter = editor_review.chapter
        editor_result = editor_review.editor_result
        eval_data = editor_review.evaluations
        decision = editor_review.decision
        edited_content = editor_review.edited_content
        raw_issues = editor_review.raw_issues

        if decision == "rewrite":
            rewrite_count += 1
            mark_editor_rewrite(
                chapter,
                rewrite_count,
                editor_result.get("rewrite_reason", ""),
                editor_result.get("rewrite_instructions", ""),
            )
            await db.commit()

            if (not runtime.enable_editor_loop) or rewrite_count >= max_rewrites:
                if not runtime.enable_force_correction:
                    await events.status(
                        AGENT_EDITOR,
                        next_chapter,
                        "编辑器要求重写，但当前流程未启用自动重写/强制修正，已暂停等待人工处理。",
                    )
                    job.current_step = "editor"
                    StateMachine.pause_job(job)
                    await db.commit()
                    return

                await events.status(
                    AGENT_EDITOR,
                    next_chapter,
                    f"重写次数已达上限（{max_rewrites}次），正在启动编辑智能体进行强制修正和润色...",
                )
                editor_review = await run_force_editor_revision(
                    db,
                    novel,
                    next_chapter,
                    chapter,
                    editor,
                    draft_content,
                    outline_data,
                    mem_context,
                    issue_summaries,
                    editor_result.get("rewrite_reason", ""),
                    validation_errors_str,
                    eval_data,
                    on_chunk=editor_cb,
                )
                decision = editor_review.decision
                edited_content = editor_review.edited_content
                raw_issues = editor_review.raw_issues
                # The forced revision is new content and must receive a fresh
                # comprehensive validation before it can be published.
                latest_validator_result = None
                await db.commit()
                break
            continue

        post_edit_validation = await run_post_edit_validation(
            db,
            novel,
            next_chapter,
            chapter,
            outline_data,
            mem_context,
            draft_content,
            edited_content,
            rewrite_count,
            max_rewrites,
            raw_issues,
            events,
            validator_agent,
            on_validator_chunk=validator_cb,
        )
        latest_validator_result = post_edit_validation.validator_result
        draft_content = post_edit_validation.draft_content
        edited_content = post_edit_validation.edited_content
        rewrite_count = post_edit_validation.rewrite_count
        decision = post_edit_validation.decision
        validation_errors_str = post_edit_validation.validation_errors
        if post_edit_validation.should_continue:
            continue
        break

    if runtime.has_editor and chapter is not None:
        style_repair = await run_style_repair(
            db,
            novel,
            next_chapter,
            chapter,
            editor,
            draft_content,
            edited_content,
            outline_data,
            mem_context,
            issue_summaries,
            events,
            on_chunk=editor_cb,
        )
        if style_repair.ran:
            edited_content = style_repair.edited_content
            # Destyled prose is new content; force a fresh comprehensive
            # validation before it can be published.
            latest_validator_result = None

    run_validator = True
    if start_step == "extractor" and chapter and chapter.status in ["validated", "post_processing"]:
        run_validator = False
        validator_result = chapter.validator_result or {"passed": True}

    if run_validator:
        await check_paused(db, job.id)
        set_job_step(job, "validator", chapter, allow_resume=True)
        await db.commit()

        await events.status(AGENT_VALIDATOR, next_chapter, "正在进行内容规则校验与字数统计...")
        chapter = await get_chapter_by_index(db, novel.id, next_chapter)

        if latest_validator_result is not None:
            validator_result = latest_validator_result
        else:
            validator_result = await run_saved_chapter_comprehensive_validation(
                db,
                novel,
                chapter,
                next_chapter,
                validator_agent,
                on_validator_chunk=validator_cb,
            )

    validator_result = await run_final_validator_flow(
        db,
        novel,
        chapter,
        next_chapter,
        attempt,
        validator_result,
        validator_agent,
        events,
        on_validator_chunk=validator_cb,
    )

    if not validator_result.get("passed") and attempt < 3:
        await check_paused(db, job.id)
        job.current_step = "writer"
        await db.commit()
        return await process_single_chapter(db, job, novel, next_chapter, attempt + 1)

    finalize_validated_chapter(chapter, validator_result)
    await db.commit()

    if validator_result.get("auto_force_saved"):
        await events.status(
            AGENT_VALIDATOR,
            next_chapter,
            "本章经过多轮重写后仍需强制保存，已暂停等待人工复核。",
        )
        job.current_step = "validator"
        StateMachine.pause_job(job)
        await db.commit()
        return

    await run_chapter_post_processing(
        db,
        job,
        novel,
        chapter,
        next_chapter,
        has_extractor=runtime.has_extractor,
        enable_living_docs_update=runtime.enable_living_docs_update,
        check_paused=check_paused,
        events=events,
    )
    from services.pipeline_commands import clear_intervention_prompt
    await clear_intervention_prompt(db, job)
