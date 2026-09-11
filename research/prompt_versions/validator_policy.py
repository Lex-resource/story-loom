"""V49–V65 的 Validator issue 分类与局部修复契约。

这些分类器在 A28/V43 生产冻结点下**恒为 False**（门起于 V49，高于 V43），对应的
修复契约构建器也随之不可达，因此整体移入研究覆盖层。函数体逐字节保持原样。

生产侧只保留 A28/V43 真正使用的两类：`is_bounded_hypothesis_issue`（有界假设）
与 `is_soft_contract_alignment_issue`（终态措辞对齐）。
"""
from __future__ import annotations

from typing import Any

from services.version_surface import NO_OVERRIDE

from research.prompt_versions.registry import register
from research.prompt_versions.version_order import prompt_version_at_least


_V49_OBSERVATION_LANGUAGE_TERMS = (
    "界面",
    "显示",
    "残缺",
    "观察",
    "真实存在",
    "原始请求",
    "发送者",
    "因果",
    "历史",
)


_V49_HARD_BOUNDARY_TERMS = (
    "与已接受事实冲突",
    "时间线矛盾",
    "物品状态矛盾",
    "地点矛盾",
    "核心事件缺失",
    "严重断章",
)


_V54_ACTION_TERMS = (
    "再次提交",
    "重复提交",
    "再次查询",
    "重复查询",
    "再次核对",
    "重复核对",
    "重复点击",
    "同一操作",
    "同一局部验证",
)


_V54_UNKNOWN_LABEL_TERMS = ("不可见", "已确认属性", "确定字段类型")


_V65_EVIDENCE_SURFACE_TERMS = (
    "设备",
    "界面",
    "显示",
    "回执",
    "脚印",
    "痕迹",
    "拖痕",
    "刻痕",
    "残片",
    "现场",
    "证据",
)


_V65_EVIDENCE_UPGRADE_TERMS = (
    "直接确认",
    "直接收束",
    "证明",
    "真实存在",
    "已经转移",
    "被带走",
    "执行者",
    "携带",
    "拖动",
    "物品性质",
    "归属",
    "因果",
    "确认成",
    "写成事实",
)


_V65_REAL_CONFLICT_TERMS = (
    "与已接受事实冲突",
    "与已发布正文冲突",
    "与冻结设定冲突",
    "时间线矛盾",
    "地点矛盾",
    "角色状态矛盾",
    "人物生死",
    "无解释复活",
    "核心事件缺失",
    "严重断章",
)


def is_v54_action_surface_issue(issue: dict[str, Any]) -> bool:
    """Identify V54's strictly local duplicate-action/unknown-label class."""
    if not prompt_version_at_least("V54") or not isinstance(issue, dict):
        return False
    text = " ".join(
        str(issue.get(key) or "")
        for key in (
            "category",
            "error_type",
            "description",
            "message",
            "evidence",
            "conflicts_with",
            "fix_suggestion",
        )
    )
    if any(term in text for term in _V49_HARD_BOUNDARY_TERMS):
        return False
    duplicate_action = any(term in text for term in _V54_ACTION_TERMS)
    unknown_label = any(term in text for term in _V54_UNKNOWN_LABEL_TERMS) and any(
        term in text for term in ("字段", "未知", "待判定", "未返回", "属性")
    )
    return duplicate_action or unknown_label


def build_v54_action_repair_contract(result: dict[str, Any]) -> str:
    """Build a sentence/action-local repair contract from Validator evidence."""
    lines = [
        "【V54 章节内动作局部修复契约】",
        "只改动作重复或未知标签，不得改动其他正文、场景顺序、人物选择和结尾状态。",
        "同一 operation 只保留第一次执行及其 response；未知字段统一改成待判定、未返回或匹配结果为空。",
        "不得新增事实、地点、角色、物品、机制、因果、身份或权限。",
    ]
    for index, issue in enumerate(result.get("hard_issues", []) or [], start=1):
        if not isinstance(issue, dict):
            continue
        lines.extend(
            [
                f"问题{index} 原文证据：{str(issue.get('evidence') or '').strip()[:1600]}",
                f"边界：{str(issue.get('conflicts_with') or '').strip()[:1600]}",
                f"局部修复：{str(issue.get('fix_suggestion') or '').strip()[:1600]}",
            ]
        )
    return "\n".join(lines)


def is_v50_minimal_observation_issue(issue: dict[str, Any]) -> bool:
    """Gate V50's sentence-local repair to V49's narrow issue class."""
    return prompt_version_at_least("V50") and is_v49_observation_language_issue(issue)


def is_v65_evidence_boundary_issue(issue: dict[str, Any]) -> bool:
    """Identify source-boundary overclaim that the Editor can patch locally."""
    if not prompt_version_at_least("V65") or not isinstance(issue, dict):
        return False
    category = str(issue.get("category") or "").strip().lower()
    if category not in {"logic", "consistency", "item_state", "continuity", "chapter_continuity"}:
        return False
    text = " ".join(
        str(issue.get(key) or "")
        for key in (
            "error_type",
            "description",
            "message",
            "evidence",
            "conflicts_with",
            "fix_suggestion",
        )
    )
    if any(term in text for term in _V65_REAL_CONFLICT_TERMS):
        return False
    return (
        any(term in text for term in _V65_EVIDENCE_SURFACE_TERMS)
        and any(term in text for term in _V65_EVIDENCE_UPGRADE_TERMS)
    )


def build_v65_evidence_boundary_repair_contract(result: dict[str, Any]) -> str:
    """Turn V65 source-boundary findings into sentence-local Editor work."""
    lines = [
        "【V65 证据边界局部修复契约】",
        "只修复 evidence 指向的越界句，保留正文其他动作、角色选择、阶段推进和结尾状态。",
        "先写可见表面，再写有限推断，最后保留待核查边界；不得新增人物、物品、地点、身份、能力、机制、授权或因果。",
    ]
    for index, issue in enumerate(result.get("hard_issues", []) or [], start=1):
        if not isinstance(issue, dict):
            continue
        lines.extend(
            [
                f"问题{index} 原句证据：{str(issue.get('evidence') or '').strip()[:1600]}",
                f"来源边界：{str(issue.get('conflicts_with') or '').strip()[:1600]}",
                f"安全替换：{str(issue.get('fix_suggestion') or '').strip()[:1600]}",
            ]
        )
    return "\n".join(lines)


def build_v50_observation_repair_contract(result: dict[str, Any]) -> str:
    """Turn Validator evidence into a bounded, sentence-local Editor contract."""
    lines = [
        "【V50 观察语言最小修复契约】",
        "只替换下面 evidence 指向的最小句子；除目标句外，必须保留其他正文、动作、节奏和结尾状态。",
        "优先采用 fix_suggestion 的安全表达，不得新增事实、身份、发送者、原始请求、因果、地点、物品、角色或机制。",
    ]
    for index, issue in enumerate(result.get("hard_issues", []) or [], start=1):
        if not isinstance(issue, dict):
            continue
        lines.extend(
            [
                f"问题{index} 原句证据：{str(issue.get('evidence') or '').strip()[:1600]}",
                f"未知边界：{str(issue.get('conflicts_with') or '').strip()[:1600]}",
                f"建议替换：{str(issue.get('fix_suggestion') or '').strip()[:1600]}",
            ]
        )
    return "\n".join(lines)


def is_v49_observation_language_issue(issue: dict[str, Any]) -> bool:
    """Identify a pure observation-to-history/causality wording repair."""
    if not prompt_version_at_least("V49") or not isinstance(issue, dict):
        return False
    category = str(issue.get("category") or "").strip().lower()
    if category not in {"logic", "consistency"}:
        return False
    text = " ".join(
        str(issue.get(key) or "")
        for key in (
            "error_type",
            "description",
            "message",
            "evidence",
            "conflicts_with",
            "fix_suggestion",
        )
    )
    if any(term in text for term in _V49_HARD_BOUNDARY_TERMS):
        return False
    return (
        sum(term in text for term in _V49_OBSERVATION_LANGUAGE_TERMS) >= 2
        and any(term in text for term in ("升级", "确认", "推断", "导致", "承认", "曾提交"))
    )


# ---------------------------------------------------------------------------
# 表面注册
# ---------------------------------------------------------------------------


@register("local_repair_issue")
def local_repair_issue(issue: "dict[str, Any]"):
    """研究版本额外归入 Editor 局部修复（因而不触发 Writer 重试）的 issue 类。"""
    return (
        is_v54_action_surface_issue(issue)
        or is_v65_evidence_boundary_issue(issue)
    )


@register("local_repair_plan")
def local_repair_plan(validator_result: "dict[str, Any]"):
    """决定是否走局部修复，以及用哪份修复契约。

    返回 None 表示不做局部修复（交回生产的常规重试判定）。
    """
    issues = [i for i in (validator_result.get("hard_issues") or []) if isinstance(i, dict)]
    if not issues:
        return None

    if prompt_version_at_least("V54") and all(is_v54_action_surface_issue(i) for i in issues):
        return {
            "kind": "action_surface",
            "repair_type": "intra_chapter_action_local_repair",
            "contract": build_v54_action_repair_contract(validator_result),
        }

    if prompt_version_at_least("V49"):
        if prompt_version_at_least("V65"):
            eligible = all(
                is_v65_evidence_boundary_issue(i) or is_v50_minimal_observation_issue(i)
                for i in issues
            )
            contract = build_v65_evidence_boundary_repair_contract(validator_result)
            repair_type = "evidence_boundary_sentence_patch"
        elif prompt_version_at_least("V50"):
            eligible = all(is_v50_minimal_observation_issue(i) for i in issues)
            contract = build_v50_observation_repair_contract(validator_result)
            repair_type = "observation_language_minimal_patch"
        else:
            eligible = all(is_v49_observation_language_issue(i) for i in issues)
            contract = None
            repair_type = "observation_language_repair"
        if eligible:
            return {"kind": "observation", "repair_type": repair_type, "contract": contract}

    return None
