"""Ariadne A5/A6/A7 的 opt-in 质量门。

只决定 A5 实验是否可以为一个硬连续性问题多花一次 Editor 调用。判据是变体轴上的
前缀匹配（`ariadne-a5` / `a6` / `a7`）——注意 `ariadne-a28` **不以** `ariadne-a5`
开头，因此这些门在 A28/V43 生产冻结点下全部为假，整个模块随之不可达。

这也是变体轴上两种写法差异的实例：数值判据 `A>=7` 在 A28 下为真（见
`research/prompt_versions/version_order.ariadne_series_at_least`），而这里的
前缀判据为假。两者不能互相替代。
"""

from __future__ import annotations

from typing import Any

from services.experiment_recorder import current, record_event

from research.prompt_versions.registry import register


def is_a5_experiment() -> bool:
    context = current()
    return bool(context and context.variant.lower().startswith("ariadne-a5"))


def is_a6_experiment() -> bool:
    """Return whether the A5 no-Polisher ablation is active."""
    context = current()
    return bool(context and context.variant.lower().startswith("ariadne-a6"))


def is_a7_experiment() -> bool:
    """Return whether the A7 contract-hygiene ablation is active."""
    context = current()
    return bool(context and context.variant.lower().startswith("ariadne-a7"))


def _issue_text(issue: dict[str, Any]) -> str:
    return " ".join(
        str(issue.get(key) or "")
        for key in ("category", "error_type", "description", "message", "conflicts_with")
    ).strip()


def assess_polisher_gate(validator_result: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic A5 gate decision with an auditable reason.

    Only explicit hard continuity/fact issues are eligible.  Warnings,
    missing evidence surfaces, style, and pacing stay on the existing local
    repair path and cannot trigger the extra call.
    """
    issues = [
        issue
        for issue in (validator_result.get("hard_issues", []) or [])
        if isinstance(issue, dict)
    ]
    if is_a6_experiment() or is_a7_experiment():
        decision = {
            "enabled": False,
            "eligible": False,
            "reason": "a6_no_extra_polisher" if is_a6_experiment() else "a7_no_extra_polisher",
            "issue_count": len(issues),
        }
        record_event(
            "a6_quality_gate" if is_a6_experiment() else "a7_quality_gate",
            {"role": "prudent", **decision},
        )
        return decision
    if not is_a5_experiment():
        return {"enabled": False, "eligible": False, "reason": "experiment_disabled", "issue_count": len(issues)}
    if validator_result.get("passed"):
        return {"enabled": True, "eligible": False, "reason": "validator_passed", "issue_count": 0}

    eligible: list[dict[str, Any]] = []
    for issue in issues:
        severity = str(issue.get("severity") or "").lower()
        category = str(issue.get("category") or "").lower()
        error_type = str(issue.get("error_type") or "")
        text = _issue_text(issue)
        is_hard = severity in {"block", "high", "critical", "error"}
        is_continuity = category in {
            "consistency",
            "timeline",
            "item_state",
            "location",
            "character_state",
            "continuity",
            "chapter_continuity",
            "logic",
            "plot",
            "core_event",
        }
        is_fact_or_timeline = any(
            marker in f"{error_type}{text}"
            for marker in ("硬冲突", "时间线", "人物状态", "角色状态", "物品状态", "核心事件", "严重断章", "因果")
        )
        if is_hard and (is_continuity or is_fact_or_timeline):
            eligible.append(issue)

    decision = {
        "enabled": True,
        "eligible": bool(eligible),
        "reason": "hard_continuity_issue" if eligible else "non_hard_or_local_issue",
        "issue_count": len(issues),
        "eligible_issue_count": len(eligible),
        "categories": sorted({str(item.get("category") or "") for item in eligible}),
    }
    record_event("a5_quality_gate", {"role": "prudent", **decision})
    return decision


def record_quality_role(role: str, *, action: str, **payload: Any) -> None:
    """Record the A5 role mapping without adding a model call."""
    record_event("a5_quality_role", {"role": role, "action": action, **payload})


# ---------------------------------------------------------------------------
# 表面注册
# ---------------------------------------------------------------------------


@register("polisher_gate")
def polisher_gate(validator_result: dict[str, Any]):
    """A5 额外 Editor 调用的门控决策。生产（A28）下 eligible 恒为 False。"""
    return assess_polisher_gate(validator_result)


@register("quality_role_event")
def quality_role_event(role: str, **fields):
    """A5/A6/A7 的质量角色事件记录。"""
    record_quality_role(role, **fields)
    return True


@register("hybrid_recall_suppressed")
def hybrid_recall_suppressed():
    """A5 消融关闭混合召回，把向量检索本身作为实验变量。"""
    return is_a5_experiment()
