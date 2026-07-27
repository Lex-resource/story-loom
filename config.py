from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from pathlib import Path
import json


POSTGRESQL_ASYNC_PREFIX = "postgresql+asyncpg://"


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
    APP_NAME: str = "novel-assistant"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://localhost:4173,http://127.0.0.1:4173,http://localhost:8000,http://127.0.0.1:8000"
    ALLOW_REMOTE_ACCESS: bool = False

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

    # LLM (fallback defaults, overridden by settings.json)
    LLM_BASE_URL: str = "https://api.deepseek.com"  # kept for backward compat; real default lives in settings_service.DEFAULT_LLM_BASE_URL
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "deepseek-v4-flash"  # aligned with settings_service.DEFAULT_LLM_MODEL
    LLM_TIMEOUT: int = 180

    # Embedding
    EMBEDDING_MODEL: str = ""
    # Optional separate endpoint/key for embeddings; fall back to LLM_* when empty.
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_API_KEY: str = ""

    # Living Docs
    LIVING_DOCS_DIR: str = str(Path(__file__).parent / "data" / "living_docs")

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
    VECTOR_OUTBOX_LEASE_SECONDS: int = 300
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


def mark_worker_process():
    """Mark the current process as a worker. Call once at worker startup.
    Also applies runtime env so worker processes get HF_ENDPOINT etc.
    """
    import os as _os
    _os.environ["IS_WORKER"] = "1"
    apply_runtime_env()
