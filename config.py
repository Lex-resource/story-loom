from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from pathlib import Path
import json


POSTGRESQL_ASYNC_PREFIX = "postgresql+asyncpg://"

# A28/V43 is the strongest completed Ariadne-continuity profile: it keeps the
# authority boundary, permits one explicitly bounded hypothesis for reversible
# investigation, and requires one observable narrative delta per chapter.
# Research jobs can still override this explicitly.
DEFAULT_CONTINUITY_PROMPT_VERSION = "V43"


def require_postgresql_url(value: str) -> str:
    if not value.startswith(POSTGRESQL_ASYNC_PREFIX):
        raise ValueError(
            "DATABASE_URL must use PostgreSQL with the asyncpg driver "
            f"({POSTGRESQL_ASYNC_PREFIX}...)"
        )
    return value


def _load_app_settings() -> dict:
    settings_file = Path(__file__).parent / "data" / "settings.json"
    if settings_file.exists():
        return json.loads(settings_file.read_text(encoding="utf-8"))
    return {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # App
    # 生产必须显式设为 false。DEBUG=true 会把完整 prompt/response payload
    # 同步落盘（agents/llm_payload.debug_log_payload），并在 500 响应里
    # 暴露异常详情。
    DEBUG: bool = False
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:3000,http://127.0.0.1:3000,http://localhost:4173,http://127.0.0.1:4173,http://localhost:8000,http://127.0.0.1:8000"
    ALLOW_REMOTE_ACCESS: bool = False
    # Required for non-local requests when ALLOW_REMOTE_ACCESS is enabled.
    REMOTE_ACCESS_TOKEN: str = ""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/novel_assistant"

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        return require_postgresql_url(value)
    # Echo every SQL statement to stdout. Kept off by default: the worker's
    # poll loops scan the DB every second, so echo floods logs with SELECTs.
    SQL_ECHO: bool = False

    # ChromaDB
    CHROMA_PERSIST_DIR: str = str(Path(__file__).parent / "data" / "chroma")
    # 启动时预热 chroma（打开 client + 读写探针 + embedding 会话建立），把
    # 最大挂死源移出热路径。失败不阻塞启动，只记健康标志。
    CHROMA_WARMUP_ENABLED: bool = True

    # Legacy recovery path only. Generation and recall no longer use files;
    # this remains so storage-repair and one-time migration tooling can inspect
    # pre-layered-memory projects without crashing on import.
    LIVING_DOCS_DIR: str = str(Path(__file__).parent / "data" / "living_docs")

    # LLM (fallback defaults, overridden by settings.json)
    LLM_BASE_URL: str = "https://api.deepseek.com"  # real default lives in services/settings_constants.DEFAULT_LLM_BASE_URL
    LLM_API_KEY: str = ""
    # 仅 .env 缺省时的兜底值。运行时生效顺序：DB provider 配置 >
    # services/settings_constants.DEFAULT_LLM_MODEL（deepseek-chat）> 此值，
    # 两处默认值不必一致。
    LLM_MODEL: str = "deepseek-v4-flash"
    # Applies to the complete HTTP/streaming call, not only an idle socket
    # read. This prevents a provider that keeps a stream open indefinitely
    # from holding a worker task forever.
    LLM_TIMEOUT: int = 180
    # Extractor post-processing can contain several JSON calls, but must still
    # have a finite wall-clock bound so a stuck task becomes recoverable.
    POST_PROCESSING_TIMEOUT_SECONDS: int = 1200

    # Embedding
    EMBEDDING_MODEL: str = ""
    # Optional separate endpoint/key for embeddings; fall back to LLM_* when empty.
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_API_KEY: str = ""

    # Data / asset directories (centralized so tests and scripts can override)
    DATA_DIR: str = str(Path(__file__).parent / "data")
    SETTINGS_FILE: str = str(Path(__file__).parent / "data" / "settings.json")
    TOKENIZER_DIR: str = str(Path(__file__).parent / "data" / "tokenizer")
    PROMPTS_DIR: str = str(Path(__file__).parent / "prompts")
    LOG_DIR: str = str(Path(__file__).parent / "logs")
    FRONTEND_DIR: str = str(Path(__file__).parent / "frontend" / "dist")

    # HuggingFace mirror (set as env var before importing transformers-adjacent libs)
    HF_ENDPOINT: str = "https://hf-mirror.com"

    # Worker
    WORKER_POLL_INTERVAL: int = 5
    MAX_CONCURRENT_JOBS: int = 3
    ORPHAN_CLEANUP_INTERVAL_SECONDS: int = 300
    # RUNNING 行多久没刷新视为孤儿/陈旧（worker 孤儿清理与 API 启动重置共用）。
    # 必须显著大于单章串行 LLM 调用总耗时，防止误杀卡在长调用里的健康任务。
    STALE_JOB_THRESHOLD_SECONDS: int = 600
    VECTOR_OUTBOX_LEASE_SECONDS: int = 300
    # false（默认）：单进程部署 —— API 进程内嵌 worker，start_backend.bat 即
    # 完整后端，无需单独开 worker.py。true：外部 worker 模式，由独立 worker.py
    # 进程消费 job（显式入口 start_worker.bat），事件广播经 HTTP 回投 API。
    # 模式切换后 API 启动会把陈旧 RUNNING job 标 FAILED（startup_recovery）；
    # uvicorn --reload 每次热重载都会触发重置，且外部 worker 并存时会造成双跑，
    # 谨慎使用。
    DISABLE_IN_PROCESS_WORKER: str = "false"
    API_INTERNAL_URL: str = "http://127.0.0.1:8000"
    # Internal token for worker→API broadcast authentication.
    # MUST be set via STREAM_INTERNAL_TOKEN env var in production.
    # Empty default means internal broadcast is only allowed from localhost.
    STREAM_INTERNAL_TOKEN: str = ""
    INTERNAL_BROADCAST_PATH: str = "/api/internal/broadcast"

    # Retry
    MAX_LLM_RETRIES: int = 3
    RETRY_DELAY: int = 5

    # Feature flags
    ENABLE_LIGHT_POLISH: bool = False
    ENABLE_NOVEL_MEMORY_EVIDENCE: bool = True
    ENABLE_NOVEL_MEMORY_ATOMS: bool = True
    ENABLE_NOVEL_MEMORY_RECALL: bool = True
    # A28/A29 production profile keeps Chroma recall advisory and disabled;
    # research jobs can opt into the hybrid path explicitly.
    ENABLE_NOVEL_HYBRID_RECALL: bool = False
    ENABLE_NOVEL_MEMORY_SCENE_BLOCKS: bool = True
    ENABLE_NOVEL_NARRATIVE_INDEX: bool = False
    # Extractor conflicts are reviewed deterministically and rejected without
    # blocking chapter publication; protected facts are never overwritten.
    ENABLE_AUTO_EXTRACTOR_REVIEW: bool = True
    # Layered memory is the only supported generation context.
    NOVEL_MEMORY_CONTEXT_MODE: str = "layered"
    # Issue summaries belong to the retired legacy context path. Keep raw
    # issues for review, but do not spend a model call rebuilding summaries in
    # the layered memory pipeline unless explicitly re-enabled.
    ENABLE_LEGACY_ISSUE_CLASSIFIER: bool = False
    # 研究专用。生产已冻结在 A28/V43（见 docs/research/novel-memory-continuity/PRODUCTION.md），
    # 生产代码里不再有版本门，因此改这个值**不会**改变生产行为——它只被
    # research/prompt_versions/ 用于复现历史实验。研究运行通过
    # job.params.experiment.prompt_version 指定版本。
    # main.py / worker.py 启动时会对偏离 V43 的取值发出 warning。
    NOVEL_CONTINUITY_PROMPT_VERSION: str = DEFAULT_CONTINUITY_PROMPT_VERSION

_settings = Settings()


def reload_settings():
    """Reload static environment settings only.

    Dynamic provider configuration is authoritative in PostgreSQL SystemSettings
    and is resolved by services.settings_store / agents.providers.
    """
    global _settings
    _settings = Settings()


# Load settings on startup
reload_settings()
settings = _settings


def apply_runtime_env():
    """Apply runtime environment variables that must be set before importing
    transformers-adjacent libraries. Call once at process startup (main/worker).
    """
    import os as _os
    _os.environ.setdefault("HF_ENDPOINT", settings.HF_ENDPOINT)


def warn_if_prompt_version_overridden() -> str | None:
    """检查 NOVEL_CONTINUITY_PROMPT_VERSION 是否被改成了非生产冻结值。

    生产代码已按 A28/V43 内联，不再读这个值，所以在 .env 里把它改成 V50 之类
    **不会**生效。返回一条 warning 文本（无异常时返回 None），由 main/worker
    在启动时记录，避免这种静默无效。
    """
    configured = str(settings.NOVEL_CONTINUITY_PROMPT_VERSION or "").upper()
    if configured == DEFAULT_CONTINUITY_PROMPT_VERSION:
        return None
    return (
        f"NOVEL_CONTINUITY_PROMPT_VERSION={configured} 不会改变生产行为："
        f"生产已冻结在 {DEFAULT_CONTINUITY_PROMPT_VERSION}，版本门已内联。"
        "研究运行请通过 job.params.experiment.prompt_version 指定版本。"
    )


def mark_worker_process():
    """Mark the current process as a worker. Call once at worker startup.
    Also applies runtime env so worker processes get HF_ENDPOINT etc.
    """
    import os as _os
    _os.environ["IS_WORKER"] = "1"
    apply_runtime_env()
