"""Shared constants for agent names, novel formats, and pipeline step names.

These were previously散落 as bare string literals across 30+ files. Centralizing
them here prevents typos and makes refactors safer.

本文件现在是兼容 facade:registry 逻辑在 agents/agent_registry.py,数值调参在
agents/tuning.py —— 两者从这里再导出,现有 `from agents.constants import X`
全部保持不变。
"""

from agents.agent_registry import (  # noqa: F401  (facade re-exports)
    AGENT_CHARACTER_CARD,
    AGENT_EDITOR,
    AGENT_EXTRACTOR,
    AGENT_PLANNER,
    AGENT_SCENE_CONSOLIDATOR,
    AGENT_VALIDATOR,
    AGENT_WRITER,
    get_default_agent,
    register_agent,
)
from agents.tuning import (  # noqa: F401  (facade re-exports)
    CHARACTER_CARD_TEMPERATURE,
    COMMUNITY_SUMMARIZER_TEMPERATURE,
    CONSOLIDATION_TEMPERATURE,
    DEFAULT_LLM_JSON_MAX_TOKENS,
    DEFAULT_LLM_JSON_TEMPERATURE,
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_LLM_TEMPERATURE,
    EDITOR_TEMPERATURE,
    EXTRACTOR_TEMPERATURE,
    ISSUE_CLASSIFIER_TEMPERATURE,
    JSON_FALLBACK_MAX_RETRIES,
    JSON_REPAIR_TIMEOUT_SECONDS,
    KEY_CHAPTER_CANDIDATE_COUNT,
    KEY_CHAPTER_STAGES,
    PAYLOAD_DEBUG_SIZE_THRESHOLD,
    PROMPT_CACHE_MAX_ENTRIES,
    PROMPT_CACHE_TTL_SECONDS,
    PROMPT_TOKEN_WARNING_THRESHOLD,
    RATE_LIMITED_RETRY_DELAY_MULTIPLIER,
    RATE_LIMITED_STATUS_CODES,
    RETRY_JITTER_RANGE,
    RAW_DOC_INLINE_THRESHOLD,
    VALIDATOR_EXTRACT_TEMPERATURE,
    VALIDATOR_MAX_TOKENS,
    VALIDATOR_TEMPERATURE,
    WRITER_MAX_TOKENS,
    WRITER_TEMPERATURE,
)

# Novel formats (stored in Novel.novel_format and PromptTemplate.category).
NOVEL_FORMAT_ZHIHU_SHORT = "zhihu_short"
NOVEL_FORMAT_LONG_WEBNOVEL = "long_webnovel"


# ---------------------------------------------------------------------------
# Prompt template name constants.
#
# Each agent's get_prompt_template(name, category=...) call previously passed
# a bare string literal. Centralizing them here:
#   1. prevents typos that silently fall back to the default template,
#   2. makes it trivial to grep for all call sites of a given template,
#   3. surfaces the full prompt-template catalog in one place.
# ---------------------------------------------------------------------------

PROMPT_PLANNER_GENERATE_SKELETON_OUTLINE = "planner_generate_skeleton_outline"
PROMPT_PLANNER_BRAINSTORM = "planner_brainstorm"
PROMPT_PLANNER_FORMAT_JSON = "planner_format_json"
PROMPT_PLANNER_GENERATE_CHAPTER_OUTLINE = "planner_generate_chapter_outline"
PROMPT_PLANNER_CHAT_MODIFY_OUTLINE = "planner_chat_modify_outline"
PROMPT_PLANNER_OPTIMIZE_SKELETON_OUTLINE = "planner_optimize_skeleton_outline"
PROMPT_PLANNER_REVIEW_ACT_RHYTHM = "planner_review_act_rhythm"
PROMPT_WRITER = "writer"
PROMPT_EDITOR_REVIEW = "editor_review"
PROMPT_EDITOR_FORCE_REVISE = "editor_force_revise"
PROMPT_EDITOR_DESTYLE = "editor_destyle"
PROMPT_VALIDATOR_VALIDATE_CONTENT = "validator_validate_content"
PROMPT_VALIDATOR_REVIEW_FULL_STORY = "validator_review_full_story"
PROMPT_VALIDATOR_EXTRACT_ENTITIES = "validator_extract_entities"
PROMPT_EXTRACTOR_SUMMARIZE_CHANGES = "extractor_summarize_changes"
PROMPT_EXTRACTOR_EXTRACT_CHANGES = "extractor_extract_changes"
PROMPT_ISSUE_CLASSIFIER_CLASSIFY_ISSUES = "issue_classifier_classify_issues"
PROMPT_COMMUNITY_SUMMARIZER = "community_summarizer"
PROMPT_CHARACTER_GENERATE_CARDS = "character_generate_cards"
PROMPT_EXTRACT_CHARACTER_CARDS = "extractor_extract_character_cards"
# 场景块整合（ENABLE_SCENE_BLOCK_CONSOLIDATION 开启时使用）
PROMPT_SCENE_BLOCK_CONSOLIDATION = "scene_block_consolidation"

CHARACTER_FACT_SOURCE_RULES = """
【角色事实时序硬规则】
1. 角色卡中的 current_state/state_at_previous_chapter 是当前章节唯一可直接使用的动态事实；只能使用截至当前章节已经发生的事实。
2. card_data 中的背景、成长路线、main_arc、side_arcs 可能包含未来规划，只能作为未来方向，绝不能当作已经发生，也不能把未来章节事件提前写入正文或动态状态。
3. 本章结束状态只能由本章正文明确发生的事件产生。没有正文证据的身份揭示、首次见面、关系升级、地点变化、能力获得、伤势恢复和物品获得，一律禁止写入。
4. 如果角色卡的未来路线与正文或当前状态冲突，优先遵守当前章节以前已发生的正文事实；不要自行修正或提前兑现未来路线。
5. 生成角色卡动态更新时，只输出本章新增或变化的字段，不复制整张卡，也不把未来计划写入 current_state。
"""

CHARACTER_CARD_EXTRACTION_RULES = """
【首次建卡规则】
1. new_character_candidates 中 card_exists=false 表示首次建卡。只为本章明确出场且具有持续剧情作用的角色输出更新；临时路人、无名群体和仅被提及的角色不要建卡。
2. 首次建卡时，必须使用 global_character_hints、chapter_outline 和正文中已有的信息生成 card_data_updates；至少填写能够确认的 identity、personality、background、speech_style、growth_route 或 main_arc，不能返回空的 card_data_updates。未知字段留空，不得猜测。
3. 首次建卡必须用 state_data 记录本章结束时正文明确显示的动态状态。已有角色卡只输出本章明确变化的字段。
4. relationships 只写本章明确新增或变化的关系。growth_route、main_arc、side_arcs 只能表达未来方向，不能伪装成已经发生的事实。
5. global_character_hints 中的角色设定可以作为稳定角色卡来源，但其中的未来情节只能写入成长路线，不能写入 current_state。
"""

# ---------------------------------------------------------------------------
# Content safety blacklist (used by agents/writing/writer.py).
# Previously in services/validator.py, moved here to avoid agents → services
# reverse dependency. services/validator.py re-exports it for backwards compat.
# ---------------------------------------------------------------------------
BLACKLIST: list[str] = [
    "作为一个AI",
    "作为语言模型",
    "根据您的要求",
    "抱歉，我无法",
    "对不起，我无法",
    "我无法满足",
    "我无法为您",
    "我无法协助",
    "作为助手",
    "以下是",
    "当然可以",
    "作为一个人工智能",
    "作为AI",
    "AI助手",
]


# ---------------------------------------------------------------------------
# Style / cliché blacklist — distinct from the safety BLACKLIST above.
# BLACKLIST is a hard-reject list for AI-refusal/meta phrases (validator errors).
# STYLE_BLACKLIST is soft guidance: AI-cliché prose the writer should avoid and
# the editor/validator should flag as writing_quality issues. Fed to the writer
# in full (not truncated) via {style_blacklist_hint}, and used by
# services/validator.py for a cliché-density heuristic.
# ---------------------------------------------------------------------------
STYLE_BLACKLIST: list[str] = [
    "空气仿佛凝固",
    "时间仿佛静止",
    "仿佛过了一个世纪",
    "不禁",
    "不由得",
    "这一刻",
    "那一刻",
    "他明白了",
    "她明白了",
    "五味杂陈",
    "百感交集",
    "嘴角勾起一抹",
    "嘴角勾起",
    "勾起一抹弧度",
    "心中一凛",
    "心头一紧",
    "眼中闪过一丝",
    "眼底闪过",
    "深吸一口气",
    "缓缓开口",
    "缓缓说道",
    "淡淡地说",
    "冷冷地说",
    "无尽的",
    "莫名的",
    "说不清道不明",
    "命运的齿轮",
    "殊不知",
    "而这一切",
    "这一切的一切",
    "仿佛整个世界",
]
