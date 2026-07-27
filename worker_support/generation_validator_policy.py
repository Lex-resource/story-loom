from __future__ import annotations

import json
from typing import Any

from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_types import PipelineStep
from services.project_stats import chapter_chars_from_row
from worker_support.generation_policy_types import ContentPair


def validation_errors_text(result: dict[str, Any]) -> str:
    if result.get("passed"):
        return ""
    return "\n".join(f"- {err}" for err in result.get("errors", []))


def target_word_count_for(novel) -> int:
    return novel.word_count_per_chapter if novel.word_count_per_chapter is not None else 3000


def apply_cleaned_content(
    result: dict[str, Any],
    draft_content: str | None,
    edited_content: str | None,
    chapter=None,
) -> ContentPair:
    if "cleaned_content" not in result:
        return ContentPair(draft_content=draft_content, edited_content=edited_content)

    cleaned = result["cleaned_content"]
    if edited_content:
        edited_content = cleaned
        if chapter is not None:
            chapter.edited_content = cleaned
    else:
        draft_content = cleaned
        if chapter is not None:
            chapter.draft_content = cleaned
    return ContentPair(draft_content=draft_content, edited_content=edited_content)


def apply_cleaned_validator_fields(result: dict[str, Any], chapter) -> None:
    if "cleaned_content" in result:
        cleaned = result["cleaned_content"]
        if chapter.edited_content:
            chapter.edited_content = cleaned
        if chapter.draft_content:
            chapter.draft_content = cleaned
    if "cleaned_title" in result:
        chapter.title = result["cleaned_title"]


def validator_fallback_text(result: dict[str, Any], chapter) -> str:
    return (
        result.get("cleaned_content")
        or chapter.edited_content
        or chapter.draft_content
        or chapter.content
        or ""
    )


def mark_validator_retry(chapter, validator_result: dict[str, Any]) -> None:
    chapter.status = "draft"
    set_chapter_pipeline_step(chapter, PipelineStep.WRITING)
    chapter.error = json.dumps(validator_result.get("errors", []), ensure_ascii=False)


def force_save_validator_result(chapter, validator_result: dict[str, Any]) -> None:
    fallback_text = validator_fallback_text(validator_result, chapter)
    apply_cleaned_validator_fields(validator_result, chapter)
    chapter.content = fallback_text
    chapter.word_count = validator_result.get("word_count") or chapter_chars_from_row(chapter)
    chapter.validator_result = {
        **validator_result,
        "passed": True,
        "auto_force_saved": True,
    }
    set_chapter_pipeline_step(chapter, PipelineStep.VALIDATING)
    chapter.status = "validated"
    chapter.error = json.dumps(
        {
            "auto_force_saved": True,
            "errors": validator_result.get("errors", []),
        },
        ensure_ascii=False,
    )


def finalize_validated_chapter(chapter, validator_result: dict[str, Any]) -> None:
    if not validator_result.get("auto_force_saved"):
        chapter.error = None
    chapter.content = chapter.edited_content or chapter.draft_content
    chapter.word_count = validator_result.get("word_count", 0)
    chapter.status = "validated"
    set_chapter_pipeline_step(chapter, PipelineStep.VALIDATING)


def validator_retry_message(chapter_index: int, attempt: int, errors: list[str]) -> str:
    err_msg = ", ".join(errors)
    return (
        f"[法则校验未通过] 第 {chapter_index} 章天道审计未通过：{err_msg}。"
        f"系统正自动带入错误原因进行重新创作（第 {attempt + 1} 轮尝试）..."
    )


def validator_force_save_message(errors: list[str]) -> str:
    return f"内容规则校验重试3次仍未通过，已自动保存当前可用版本并继续：{', '.join(errors)}"
