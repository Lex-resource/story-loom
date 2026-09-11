from __future__ import annotations

import json
from typing import Any

from services.pipeline_transitions import set_chapter_pipeline_step
from services.pipeline_types import PipelineStep
from services.project_stats import chapter_chars_from_row
from worker_support.generation_policy_types import ContentPair
from services.experiment_recorder import record_content_retry
from services.validation_constants import RETRYABLE_CATEGORIES, is_fact_conflict_issue
from services.version_surface import NO_OVERRIDE, research_override
from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override


def validation_errors_text(result: dict[str, Any]) -> str:
    if result.get("passed"):
        return ""
    lines = [f"- {err}" for err in result.get("errors", [])]
    for issue in result.get("hard_issues", []) or []:
        if not isinstance(issue, dict):
            continue
        detail = (
            f"- 证据定位：类别={issue.get('category', '')}；"
            f"类型={issue.get('error_type', '')}；"
            f"正文证据={issue.get('evidence', '')}；"
            f"冲突事实={issue.get('conflicts_with', '')}；"
            f"修复建议={issue.get('fix_suggestion', '')}"
        )
        if detail not in lines:
            lines.append(detail)
    return "\n".join(lines)


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


def _is_research_local_repair_issue(issue: dict[str, Any]) -> bool:
    """研究版本是否把该 issue 额外归入 Editor 局部修复路径。

    A28/V43 生产只把"有界假设措辞"一类留在局部修复路径（见
    `is_bounded_hypothesis_issue`）；V49–V65 引入的观察语言与动作面两类
    在生产冻结点下不适用，因此由研究覆盖层判定。
    """
    override = research_override("local_repair_issue", issue)
    return bool(override) if override is not NO_OVERRIDE else False


def has_fact_conflict(result: dict[str, Any]) -> bool:
    return any(
        is_fact_conflict_issue(issue) and not _is_research_local_repair_issue(issue)
        for issue in result.get("hard_issues", [])
        if isinstance(issue, dict)
    )


_V5_RETRYABLE_TERMS = (
    "核心事件",
    "严重断章",
    "断章",
    "主线缺失",
    "因果颠倒",
    "时间线",
    "硬冲突",
)
_V20_LOCAL_REPAIR_TERMS = (
    "字段缺失",
    "未登记",
    "没有登记",
    "证据清单不完整",
    "术语混用",
    "术语不一致",
    "重复登记",
    "说明书式",
    "来源字段",
    "读取路径",
    "证明范围",
)
_V40_SOFT_CONTRACT_TERMS = (
    "轻微表述歧义",
    "语义歧义",
    "契约措辞",
    "契约表述",
    "统一章节结尾状态",
    "不构成硬冲突",
)
_V40_HARD_CONTRACT_TERMS = (
    "与已接受事实冲突",
    "时间线矛盾",
    "物品状态矛盾",
    "地点矛盾",
    "核心事件缺失",
    "严重断章",
)
_KNOWN_VALIDATOR_CATEGORIES = frozenset(
    {"logic", "consistency", "pacing", "payoff", "viewpoint", "style", "character", "timeline"}
)


_V43_HYPOTHESIS_TERMS = (
    "假设",
    "待核实",
    "工作解释",
    "候选线索",
    "candidate",
    "unknown",
)


















def is_bounded_hypothesis_issue(issue: dict[str, Any]) -> bool:
    """把明确标注为"假设/待核实"的措辞问题留在局部修复路径。

    这是 A28/V43 的核心特性，也是 PRODUCTION.md 记录的零内容重试指标的来源。
    原先由 `variant` 以 `ariadne-a28` 开头才启用；生产已冻结在 A28，因此无条件生效。
    """
    text = " ".join(
        str(issue.get(key) or "")
        for key in (
            "category",
            "error_type",
            "description",
            "message",
            "evidence",
            "fix_suggestion",
        )
    ).lower()
    if not any(term.lower() in text for term in _V43_HYPOTHESIS_TERMS):
        return False
    return not any(
        term in text
        for term in (
            "与已接受事实冲突",
            "时间线矛盾",
            "物品状态矛盾",
            "地点矛盾",
            "核心事件缺失",
            "严重断章",
        )
    )


def is_soft_contract_alignment_issue(issue: dict[str, Any]) -> bool:
    """Keep wording-only terminal-state alignment from using a Writer retry."""
    text = " ".join(
        str(issue.get(key) or "")
        for key in (
            "category",
            "error_type",
            "description",
            "message",
            "evidence",
            "fix_suggestion",
        )
    )
    return (
        any(term in text for term in _V40_SOFT_CONTRACT_TERMS)
        and not any(term in text for term in _V40_HARD_CONTRACT_TERMS)
    )




def _retryable_categories(novel_format: str | None) -> frozenset[str]:
    """该工作流里哪些类别的阻断级问题值得退回 Writer 重写。

    长篇（及一切继承 frozen_v43 的自定义工作流）让路到 A28/V43 基线。短篇的 validator
    模板产出 `logic|consistency|pacing|payoff|viewpoint`（prompts/validation/
    zhihu_short_validation.json），其中 `viewpoint`（人称越权）与 `payoff`（开篇承诺被
    违背）是短篇表面明确宣布的四种 block 中的两种，却都不在长篇词表里 —— 于是
    `requires_content_retry` 返回 False，缺陷正文走 `force_save_validator_result` 直接落盘
    并被标成 `passed=True`。格式轴接管这份词表就是为了修掉这条。
    """
    override = workflow_override("retry_categories", novel_format)
    if override is not NO_WORKFLOW_OVERRIDE:
        return frozenset(override)
    return RETRYABLE_CATEGORIES


def requires_content_retry(result: dict[str, Any], novel_format: str | None = None) -> bool:
    """Return whether a failed validation warrants another Writer draft in V5.

    `novel_format` 缺省为 None → 走长篇基线，保守：调用点忘了传不会放宽判定。
    """
    retryable_categories = _retryable_categories(novel_format)
    if result.get("passed"):
        return False
    issues = [
        issue for issue in (result.get("hard_issues", []) or [])
        if isinstance(issue, dict)
        and not is_bounded_hypothesis_issue(issue)
        and not _is_research_local_repair_issue(issue)
    ]
    issues = [issue for issue in issues if not is_soft_contract_alignment_issue(issue)]
    if not issues:
        # Validator 只返回 errors、未能结构化 hard_issues 时，仍代表正文未通过。
        # 不能因为分类缺失就把失败稿自动 force-save。
        return bool(result.get("errors"))
    if issues:
        # V20 treats isolated evidence-surface omissions as Editor-local work.
        # A fact-conflict signal in the same issue still wins below.
        for issue in issues:
            text = " ".join(
                str(issue.get(key) or "")
                for key in ("category", "error_type", "description", "message")
            )
            category = str(issue.get("category") or "").strip().lower()
            severity = str(issue.get("severity") or "").strip().lower()
            if category not in _KNOWN_VALIDATOR_CATEGORIES and severity in {
                "block",
                "error",
                "fatal",
            }:
                return True
            if any(term in text for term in _V20_LOCAL_REPAIR_TERMS):
                continue
            if is_fact_conflict_issue(issue):
                return True
    if has_fact_conflict(result):
        non_local_issues = []
        for issue in issues:
            text = " ".join(
                str(issue.get(key) or "")
                for key in ("category", "error_type", "description", "message")
            )
            if not any(term in text for term in _V20_LOCAL_REPAIR_TERMS):
                non_local_issues.append(issue)
        if non_local_issues:
            return True
    for issue in result.get("hard_issues", []) or []:
        if not isinstance(issue, dict):
            continue
        if is_bounded_hypothesis_issue(issue):
            continue
        if _is_research_local_repair_issue(issue):
            continue
        category = str(issue.get("category") or "").strip().lower()
        error_type = str(issue.get("error_type") or "")
        description = str(issue.get("description") or issue.get("message") or "")
        if any(
            term in f"{error_type}{description}"
            for term in _V20_LOCAL_REPAIR_TERMS
        ):
            continue
        if category in retryable_categories:
            return True
        if any(term in f"{error_type}{description}" for term in _V5_RETRYABLE_TERMS):
            return True
        # 未知阻断类别也必须回 Writer；只有明确识别为局部/观察项的问题
        # 才允许留在 Editor 路径。
        if (
            category not in _KNOWN_VALIDATOR_CATEGORIES
            and str(issue.get("severity") or "").lower() in {"block", "error", "fatal"}
        ):
            return True
    return False


def mark_validator_retry(chapter, validator_result: dict[str, Any]) -> None:
    chapter.status = "draft"
    set_chapter_pipeline_step(chapter, PipelineStep.WRITING)
    chapter.error = json.dumps(validator_result.get("errors", []), ensure_ascii=False)
    record_content_retry(
        "validator_blocked",
        json.dumps(validator_result.get("errors", []), ensure_ascii=False),
    )


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
