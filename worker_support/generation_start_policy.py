from __future__ import annotations

from typing import Any

from worker_support.generation_policy_types import GenerationLoopState, GenerationStartState


def resolve_generation_start_state(
    job,
    chapter,
    job_params: dict[str, Any] | None,
    *,
    has_editor: bool,
) -> GenerationStartState:
    start_step = job.current_step or "planner"
    if start_step == "editor" and not has_editor:
        start_step = "validator" if chapter_has_content(chapter) else "writer"
        job.current_step = start_step

    if should_advance_from_planner_to_writer(start_step, chapter, job_params):
        start_step = "writer"
        job.current_step = start_step

    use_existing_outline = start_step != "planner"
    custom_prompt = None
    if job_params:
        if "use_existing_outline" in job_params:
            use_existing_outline = job_params.get("use_existing_outline")
        custom_prompt = job_params.get("custom_prompt")

    return GenerationStartState(
        start_step=start_step,
        use_existing_outline=use_existing_outline,
        custom_prompt=custom_prompt,
    )


def initial_generation_loop_state(
    chapter,
    start_step: str,
    *,
    max_rewrites: int,
) -> GenerationLoopState:
    draft_content = chapter.draft_content if chapter else None
    edited_content = chapter.edited_content if chapter else None
    rewrite_count = (chapter.rewrite_count or 0) if chapter else 0
    skip_write_edit = start_step in ["validator", "extractor"] and bool(draft_content)

    return GenerationLoopState(
        draft_content=draft_content,
        edited_content=edited_content,
        rewrite_count=max_rewrites if skip_write_edit else rewrite_count,
        max_rewrites=max_rewrites,
        decision="none" if skip_write_edit else initial_generation_decision(start_step),
        validation_errors="",
        latest_validator_result=None,
        raw_issues=[],
        skip_write_edit=skip_write_edit,
    )


def initial_generation_decision(start_step: str) -> str:
    return "revise" if start_step == "editor" else "rewrite"


def chapter_has_content(chapter) -> bool:
    return bool(chapter and (chapter.edited_content or chapter.draft_content or chapter.content))


def should_advance_from_planner_to_writer(
    start_step: str,
    chapter,
    job_params: dict[str, Any] | None,
) -> bool:
    if start_step != "planner" or not chapter or not chapter.outline:
        return False
    if job_params and job_params.get("use_existing_outline") is False:
        return False
    return not chapter.draft_content
