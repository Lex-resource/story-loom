"""Shared constants for agent names, novel formats, and pipeline step names.

These were previously散落 as bare string literals across 30+ files. Centralizing
them here prevents typos and makes refactors safer.
"""

# Canonical agent / pipeline node names.
# Used by: agents/pipeline.py, worker_support/*, services/*,
# routers/settings.py, frontend store.
AGENT_PLANNER = "planner"
AGENT_WRITER = "writer"
AGENT_EDITOR = "editor"
AGENT_VALIDATOR = "validator"
AGENT_EXTRACTOR = "extractor"
AGENT_CHARACTER_CARD = "character_card"
# 记忆整合不是流水线节点，只是 post-processing 里的辅助调用；
# 独立命名是为了 usage 统计里能区分整合成本，不与 extractor 混算。
AGENT_SCENE_CONSOLIDATOR = "scene_consolidator"

# 五个 agent 的规范顺序在 `services/pipeline_stages.CANONICAL_AGENT_ORDER` —— 它同时是
# `PipelineStep` 顺序的派生依据，所以那里是唯一来源。这里不再放第二份同样的列表。


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------
# Maps agent name -> zero-arg factory callable that returns a default AgentBase
# instance. PipelineNode subclasses look up their default agent here instead of
# hard-coding `_default_planner()` etc., so adding a new agent only requires
# registering a factory in one place.
#
# Factories are stored as lazy strings+callables to avoid importing every agent
# class at module load time (which would create circular imports because agents
# import from agents.constants).

_AGENT_REGISTRY: dict[str, "callable"] = {}

# Whether _bootstrap_default_agents() has been invoked yet.
#
# Bootstrap MUST be lazy: doing it at module load creates a circular import
# (agents.constants -> agents.writing.* -> agents.base -> agents.constants)
# that fails because agents.base.AgentBase is not yet defined when the
# writing-agent modules try to import it. Triggering on first
# get_default_agent() call defers the writing-agent imports until *all* of
# agents.base has finished loading, which breaks the cycle.
_AGENT_BOOTSTRAP_DONE: bool = False


def register_agent(name: str, factory: "callable") -> None:
    """Register a default-agent factory under the given agent name.

    Idempotent: re-registering the same name overwrites the previous factory.
    """
    _AGENT_REGISTRY[name] = factory


def get_default_agent(name: str):
    """Return a fresh default agent instance for *name*.

    Triggers :func:`_bootstrap_default_agents` on first call to populate the
    built-in agent factories. Raises ``KeyError`` if *name* is not a registered
    agent.
    """
    global _AGENT_BOOTSTRAP_DONE
    if not _AGENT_BOOTSTRAP_DONE:
        _bootstrap_default_agents()
        _AGENT_BOOTSTRAP_DONE = True
    if name not in _AGENT_REGISTRY:
        raise KeyError(
            f"No default agent factory registered for {name!r}. "
            f"Call register_agent({name!r}, factory) first. "
            f"Known agents: {sorted(_AGENT_REGISTRY)}"
        )
    return _AGENT_REGISTRY[name]()


def _bootstrap_default_agents() -> None:
    """Register the built-in default agent factories.

    Imports are local to keep agents.constants free of circular dependencies.
    Triggered lazily on first :func:`get_default_agent` call (not at module
    load) so that agents.base is fully loaded by the time the writing-agent
    modules need to import ``AgentBase`` from it.
    """
    from agents.writing.planner import PlannerAgent
    from agents.writing.writer import WriterAgent
    from agents.writing.editor import EditorAgent
    from agents.writing.validator_agent import ValidatorAgent
    from agents.writing.extractor import ExtractorAgent

    register_agent(AGENT_PLANNER, PlannerAgent)
    register_agent(AGENT_WRITER, WriterAgent)
    register_agent(AGENT_EDITOR, EditorAgent)
    register_agent(AGENT_VALIDATOR, ValidatorAgent)
    register_agent(AGENT_EXTRACTOR, ExtractorAgent)

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
CHARACTER_CARD_TEMPERATURE: float = 0.25
CONSOLIDATION_TEMPERATURE: float = 0.2

# Per-agent max_tokens overrides for non-JSON call_llm paths.
# (JSON paths use DEFAULT_LLM_JSON_MAX_TOKENS from below.)
WRITER_MAX_TOKENS: int = 8192
VALIDATOR_MAX_TOKENS: int = 2048

# When a living-doc's full text is at or below this length, feed the writer the
# full doc (raw_*) instead of the RAG-truncated version. Short docs fit in the
# prompt budget whole, so retrieval only risks dropping setting the writer needs
# (e.g. a character not surfaced by the vector query). Above it, keep RAG.
RAW_DOC_INLINE_THRESHOLD: int = 6000

# Candidate-generation ("best-of-N") for key chapters. On high-tension chapters
# (narrative_stage in KEY_CHAPTER_STAGES) the writer drafts this many candidates
# and the deterministic style scorer picks the best-reading one. 1 disables it
# (single draft, original behaviour); values >1 trade API cost for prose quality
# only where it matters most — the climaxes readers remember.
KEY_CHAPTER_CANDIDATE_COUNT: int = 1
KEY_CHAPTER_STAGES: tuple[str, ...] = ("冲突升级", "高潮")

# Fallback retry count for the internal _handle_streaming_response path
# when the caller does not supply a retry budget. Kept tiny because this
# path is only used to recover a truncated stream, not for full retries.
JSON_FALLBACK_MAX_RETRIES: int = 1

# ---------------------------------------------------------------------------
# LLM call defaults and behavioral thresholds (used by agents/base.py).
# Previously hardcoded as magic numbers; centralized here for clarity and tuning.
# ---------------------------------------------------------------------------

# Default sampling params for call_llm (free-form text generation).
DEFAULT_LLM_TEMPERATURE: float = 0.7
DEFAULT_LLM_MAX_TOKENS: int = 4096

# Default sampling params for call_llm_json (structured JSON generation).
# Lower temperature for more deterministic JSON output; larger max_tokens for
# structured payloads which tend to be longer.
DEFAULT_LLM_JSON_TEMPERATURE: float = 0.3
DEFAULT_LLM_JSON_MAX_TOKENS: int = 8192

# Per-agent temperature presets. Centralized so all agents of the same type
# use a consistent value and can be tuned from one place.
WRITER_TEMPERATURE: float = 0.75       # creative writing — needs fluency
EDITOR_TEMPERATURE: float = 0.3        # revision — deterministic edits
VALIDATOR_TEMPERATURE: float = 0.2     # validation — strict judgment
VALIDATOR_EXTRACT_TEMPERATURE: float = 0.1  # entity extraction — most strict
EXTRACTOR_TEMPERATURE: float = 0.2     # knowledge extraction — strict
ISSUE_CLASSIFIER_TEMPERATURE: float = 0.2   # issue classification — strict
COMMUNITY_SUMMARIZER_TEMPERATURE: float = 0.3  # summarization — balanced

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

# Prompt input-token warning threshold. Above this we broadcast a cost warning
# to the frontend so the user can monitor API spend.
PROMPT_TOKEN_WARNING_THRESHOLD: int = 35000

# PromptTemplate in-memory cache TTL (seconds). 正常路径的新鲜度由
# prompt_templates 表版本戳保证（services/config_versions.py），TTL 只在
# 戳查询不可用（DB 抖动/迁移未跑）时兜底。
PROMPT_CACHE_TTL_SECONDS: int = 300

# Hard upper bound on the number of entries kept in the in-memory
# PromptTemplate cache. The cache is keyed by (name, category); in practice
# the working set is small (a few dozen templates), but a cap prevents
# unbounded growth if many distinct categories are queried at runtime.
PROMPT_CACHE_MAX_ENTRIES: int = 256

# Payload debug-logging threshold (bytes). When DEBUG is on and the serialized
# request payload exceeds this size, the full payload is also dumped to
# logs/huge_payload.json for offline inspection.
PAYLOAD_DEBUG_SIZE_THRESHOLD: int = 1_000_000

# HTTP status codes that should be treated as rate-limiting / transient server
# overload and thus trigger a longer retry backoff.
RATE_LIMITED_STATUS_CODES: tuple[int, ...] = (429, 503)

# Multiplier applied to the base retry delay when a rate-limited status code is
# encountered (in addition to the normal exponential backoff).
RATE_LIMITED_RETRY_DELAY_MULTIPLIER: int = 3

# Jitter range (multiplier) applied to the exponential backoff delay to avoid
# thundering-herd retries. random.uniform(*RETRY_JITTER_RANGE).
RETRY_JITTER_RANGE: tuple[float, float] = (0.5, 1.5)

# Timeout (seconds) for the json_repair fallback when parsing malformed JSON
# responses from the LLM.
JSON_REPAIR_TIMEOUT_SECONDS: float = 10.0

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


# NOTE: _bootstrap_default_agents() is intentionally NOT called at module load.
# It is triggered lazily by get_default_agent() on first use. Calling it here
# creates a circular import (agents.constants -> agents.writing.* ->
# agents.base -> agents.constants) that fails because AgentBase is not yet
# defined when the writing-agent modules try to import it. See the comment on
# _AGENT_BOOTSTRAP_DONE above for the full rationale.
