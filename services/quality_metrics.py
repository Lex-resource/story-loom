"""Seven-dimension quality metrics used by continuity experiments."""

from __future__ import annotations

from typing import Any


QUALITY_DIMENSIONS: tuple[str, ...] = (
    "plot_progression",
    "character_portrayal",
    "world_consistency",
    "writing_quality",
    "logical_coherence",
    "chapter_continuity",
    "foreshadowing_payoff",
)

# 长篇门槛维度（研究质量门要求跨章衔接与伏笔兑现不低于 8.5）。
LONG_FORM_GATE_MINIMUMS: dict[str, float] = {
    "chapter_continuity": 8.5,
    "foreshadowing_payoff": 8.5,
}


def dimensions_for(novel_format: str | None = None) -> tuple[str, ...]:
    """该工作流的质量维度集。长篇（及未知格式）用冻结的七维。

    短篇由格式轴换成「五维手艺 + 两维分节」（hook_strength / emotional_landing），
    这样短篇 Editor 逐节打的分终于齐全，``quality_summary`` 才能 complete=true，
    短篇也才有可比较的质量指标。
    """
    from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override

    override = workflow_override("quality_dimensions", novel_format)
    if override is not NO_WORKFLOW_OVERRIDE:
        return tuple(override)
    return QUALITY_DIMENSIONS


def gate_minimums_for(novel_format: str | None = None) -> dict[str, float]:
    """该工作流的门槛维度及其下限。"""
    from services.workflow_surface import NO_WORKFLOW_OVERRIDE, workflow_override

    override = workflow_override("quality_gate_minimums", novel_format)
    if override is not NO_WORKFLOW_OVERRIDE:
        return dict(override)
    return LONG_FORM_GATE_MINIMUMS


def normalize_evaluations(
    evaluations: dict[str, Any] | None,
    novel_format: str | None = None,
) -> dict[str, dict[str, Any]]:
    raw = evaluations if isinstance(evaluations, dict) else {}
    normalized: dict[str, dict[str, Any]] = {}
    for dimension in dimensions_for(novel_format):
        value = raw.get(dimension)
        if not isinstance(value, dict) or "score" not in value:
            continue
        try:
            score = max(1, min(10, int(value["score"])))
        except (TypeError, ValueError):
            continue
        normalized[dimension] = {
            "score": score,
            "reason": str(value.get("reason") or ""),
        }
    return normalized


def quality_summary(
    evaluations: dict[str, Any] | None,
    novel_format: str | None = None,
) -> dict[str, Any]:
    dims = dimensions_for(novel_format)
    scores = normalize_evaluations(evaluations, novel_format)
    values = [item["score"] for item in scores.values()]
    average = round(sum(values) / len(values), 2) if values else None
    return {
        "dimensions": scores,
        "dimension_count": len(values),
        "average": average,
        "complete": len(values) == len(dims),
    }


def meets_quality_gate(
    summary: dict[str, Any],
    novel_format: str | None = None,
) -> bool:
    dimensions = summary.get("dimensions") or {}
    if not summary.get("complete") or (summary.get("average") or 0) < 8.5:
        return False
    for dimension, minimum in gate_minimums_for(novel_format).items():
        if (dimensions.get(dimension) or {}).get("score", 0) < minimum:
            return False
    return all(
        (dimensions.get(dimension) or {}).get("score", 0) >= 8.0
        for dimension in dimensions_for(novel_format)
    )
