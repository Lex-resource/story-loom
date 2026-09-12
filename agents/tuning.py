"""LLM 调参常量:温度、token 上限、重试与缓存阈值。

从 agents/constants.py 拆出 —— 这些值都是"数值调参",和提示词名/agent 名的
变更节奏完全不同,单独一个文件让调参 review 只看这里。constants.py 再导出
全部名字,现有导入不需要改。
"""

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
