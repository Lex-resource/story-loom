from __future__ import annotations

import json
from typing import Any

from services.novel_constants import (
    EDITOR_DECISION_PROCEED,
    EDITOR_DECISION_REWRITE,
    EDITOR_DECISION_REVISE,
)
from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_types import PipelineStep
from services.project_stats import chapter_chars_from_row
from worker_support.validation import min_score_from_evaluations, resolve_editor_decision
from services.experiment_recorder import record_content_retry
from core.pipeline_vocab import ChapterStatus

_HARD_EDITOR_CATEGORIES = {
    "logic",
    "consistency",
    "timeline",
    "item_state",
    "location",
    "character_state",
}


def _has_explicit_hard_editor_issue(editor_result: dict[str, Any]) -> bool:
    for issue in editor_result.get("raw_issues", []) or []:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "").lower()
        category = str(issue.get("category") or "").lower()
        if severity in {"block", "high", "critical"} and category in _HARD_EDITOR_CATEGORIES:
            return True
    return False


def resolve_editor_decision_from_result(
    editor_result: dict[str, Any],
    rewrite_count: int,
) -> str:
    raw_decision = str(editor_result.get("decision") or "").strip().lower()
    if raw_decision == "accept":
        raw_decision = EDITOR_DECISION_PROCEED
    if raw_decision in {EDITOR_DECISION_PROCEED, EDITOR_DECISION_REVISE}:
        return raw_decision
    if raw_decision == EDITOR_DECISION_REWRITE:
        if _has_explicit_hard_editor_issue(editor_result):
            return EDITOR_DECISION_REWRITE
        if rewrite_count > 0:
            return EDITOR_DECISION_REWRITE
        return EDITOR_DECISION_REVISE

    eval_data = editor_result.get("evaluations", {})
    if eval_data and isinstance(eval_data, dict):
        if str(editor_result.get("edited_content") or "").strip():
            return EDITOR_DECISION_PROCEED
        min_score = min_score_from_evaluations(eval_data)
        return resolve_editor_decision(min_score, rewrite_count, editor_result)

    return EDITOR_DECISION_REVISE


def editor_edited_content(editor_result: dict[str, Any], draft_content: str | None) -> str:
    edited_content = editor_result.get("edited_content", draft_content)
    if not (edited_content or "").strip():
        return draft_content or ""
    return edited_content


def apply_editor_revision(
    chapter,
    draft_content: str | None,
    edited_content: str | None,
    decision: str,
    evaluations: dict[str, Any],
) -> None:
    chapter.draft_content = draft_content
    chapter.edited_content = edited_content
    chapter.editor_decision = decision
    chapter.evaluations = evaluations


def mark_editor_skipped(
    chapter,
    draft_content: str | None,
    edited_content: str | None,
    validator_result: dict[str, Any],
) -> None:
    chapter.draft_content = draft_content
    chapter.edited_content = edited_content
    chapter.editor_decision = "skipped"
    chapter.evaluations = {}
    chapter.error = (
        None
        if validator_result.get("passed")
        else json.dumps(validator_result.get("errors", []), ensure_ascii=False)
    )


def mark_editor_success(chapter, rewrite_count: int) -> None:
    chapter.error = None
    chapter.rewrite_count = rewrite_count


def mark_editor_rewrite(
    chapter,
    rewrite_count: int,
    rewrite_reason: str,
    rewrite_instructions: str,
) -> None:
    chapter.rewrite_count = rewrite_count
    chapter.error = json.dumps(
        {
            "rewrite_reason": rewrite_reason,
            "rewrite_instructions": rewrite_instructions,
        },
        ensure_ascii=False,
    )
    chapter.status = ChapterStatus.DRAFT
    record_content_retry(rewrite_reason, rewrite_instructions)


def mark_force_corrected_revision(
    chapter,
    edited_content: str,
    editor_result: dict[str, Any],
    fallback_evaluations: dict[str, Any],
) -> None:
    chapter.edited_content = edited_content
    chapter.editor_decision = EDITOR_DECISION_REVISE
    chapter.error = None
    chapter.force_corrected = True
    chapter.evaluations = editor_result.get("evaluations", fallback_evaluations)


def force_save_after_quick_validation_failure(chapter) -> None:
    chapter.error = None
    chapter.content = chapter.edited_content or chapter.draft_content
    chapter.word_count = chapter_chars_from_row(chapter)
    chapter.status = ChapterStatus.VALIDATED
    set_chapter_pipeline_step(chapter, PipelineStep.VALIDATING)
    chapter.force_corrected = True
