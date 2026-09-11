"""Validation phase and issue severity constants."""

VALIDATION_MODE_QUICK_POST_EDIT: str = "quick_post_edit"
VALIDATION_PHASE_QUICK: str = "quick"
VALIDATION_PHASE_LLM: str = "llm"
ISSUE_SEVERITY_BLOCK: str = "block"
ISSUE_SEVERITY_WARNING: str = "warning"
VALIDATOR_DEFAULT_CATEGORY: str = "逻辑"

# These categories describe contradictions with persisted story facts. They
# must never be downgraded to a non-blocking style or quality warning.
FACT_CONFLICT_CATEGORIES = frozenset({
    "consistency",
    "timeline",
    "item_state",
    "location",
})
FACT_CONFLICT_ERROR_TYPES = frozenset({
    "人物特征矛盾",
    "时间线矛盾",
    "物品状态矛盾",
    "地点矛盾",
    "因果颠倒",
})


def is_fact_conflict_issue(issue: dict) -> bool:
    category = str(issue.get("category") or "").strip().lower()
    error_type = str(issue.get("error_type") or "").strip()
    return category in FACT_CONFLICT_CATEGORIES or error_type in FACT_CONFLICT_ERROR_TYPES


# 这些类别的阻断级问题值得退回 Writer 重写一版（A28/V43 的长篇基线，原
# `worker_support.generation_validator_policy._V5_RETRYABLE_CATEGORIES`）。放在这里是为了
# 让格式轴的短篇实现（services/short_form_surfaces.py 的 `retry_categories` 表面）能引用
# 同一份基线 —— `services/` 不得导入 `worker_support/`。
RETRYABLE_CATEGORIES = frozenset({
    "consistency",
    "timeline",
    "item_state",
    "location",
    "logic",
    "continuity",
    "chapter_continuity",
    "plot",
    "structure",
    "core_event",
})
