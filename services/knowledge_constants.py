"""Knowledge graph, patch, and classification constants."""

FORESHADOWING_STATUS_ACTIVE: str = "active"
FORESHADOWING_STATUS_RESOLVED: str = "resolved"
FORESHADOWING_STATUS_CANCELLED: str = "cancelled"
FORESHADOWING_DEFAULT_IMPORTANCE: str = "medium"

PROTAGONIST_ROLE_LABEL: str = "主角"

PATCH_CATEGORY_CHARACTER: str = "character"
PATCH_CATEGORY_WORLD_RULE: str = "world_rule"
PATCH_CATEGORY_FORESHADOWING: str = "foreshadowing"
PATCH_CATEGORY_PLOT_THREAD: str = "plot_thread"

CHARACTER_GROUP_PROTAGONIST: str = "主角"
CHARACTER_GROUP_ANTAGONIST: str = "反派"
CHARACTER_GROUP_SUPPORTING: str = "配角"

WORLD_RULE_ROOT_LABEL: str = "世界设定"
WORLD_RULE_CATEGORIES: dict[str, str] = {
    "rule": "编译法则",
    "location": "运行空间",
    "faction": "活动线程",
    "restriction": "限制禁忌",
}

CHARACTER_DISPLAY_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "性别", "首次出场", "最后出场", "是否存活",
    "立场", "阵营", "身份", "能力", "位置",
    "心理", "弱点", "目标", "状态",
)

KNOWLEDGE_TIMESTAMP_FORMAT: str = "%Y-%m-%d %H:%M"
PLOT_THREAD_PROGRESS_MAX_CHARS: int = 150

# 承诺-张力图谱：债务是伏笔的泛化。债务类型存于 KnowledgeBase.attributes["debt_type"]，
# 复用伏笔的 chapter(欠债起始) / resolved_chapter(预期兑现章) / status 语义。
DEBT_TYPE_FORESHADOWING: str = "foreshadowing"  # 伏笔（既有默认）
DEBT_TYPE_SUSPENSE: str = "suspense"            # 悬念
DEBT_TYPE_HUMILIATION: str = "humiliation"      # 打脸/憋屈待爆发
DEBT_TYPE_GOAL: str = "goal"                    # 主角目标待达成
DEBT_TYPE_LABELS: dict[str, str] = {
    DEBT_TYPE_FORESHADOWING: "伏笔到期",
    DEBT_TYPE_SUSPENSE: "悬念待揭",
    DEBT_TYPE_HUMILIATION: "打脸待爆发",
    DEBT_TYPE_GOAL: "目标待达成",
}
