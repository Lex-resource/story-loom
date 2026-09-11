import asyncio
import logging
import uuid
from typing import Optional

import httpx

from config import settings
from database import async_session
from models.novel import TokenUsage
from services.runtime_tunables_service import get_value
from services.vector_constants import AGENT_NAME_EMBEDDING
from services.shared_http import get_shared_client
from agents.constants import RATE_LIMITED_STATUS_CODES
from agents.providers import resolve_active_provider
from services.provider_testing import validate_provider_base_url

logger = logging.getLogger(__name__)


async def _post_embeddings(url: str, headers: dict, payload: dict) -> httpx.Response:
    """瞬时故障（429/5xx/网络错误）的小重试：一次抖动不该让整个 outbox 条目
    走失败重放。延迟曲线复用 LLM 侧的 compute_retry_delay（含 429 倍率）。
    次数/超时/退避入库（runtime_tunables），每次请求与每次重试时读取。
    """
    from agents.retry_policy import compute_retry_delay

    max_attempts = await get_value("embedding_max_attempts")
    timeout_seconds = await get_value("embedding_timeout_seconds")
    for attempt in range(max_attempts):
        try:
            resp = await get_shared_client().post(
                url, headers=headers, json=payload, timeout=timeout_seconds
            )
            resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            retryable = isinstance(exc, httpx.TransportError) or (
                isinstance(exc, httpx.HTTPStatusError)
                and (
                    exc.response.status_code in RATE_LIMITED_STATUS_CODES
                    or exc.response.status_code >= 500
                )
            )
            if not retryable or attempt >= max_attempts - 1:
                raise
            delay = compute_retry_delay(
                exc,
                attempt,
                max_attempts,
                base_retry_delay=await get_value("embedding_retry_base_delay_seconds"),
            )
            logger.warning(
                "embedding_request_retry attempt=%s delay_seconds=%.2f error=%s",
                attempt + 1,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")  # pragma: no cover


async def resolve_embedding_provider() -> tuple[str, str, str | None]:
    """Resolve embeddings from the active provider, with env compatibility.

    Provider settings are dynamic and database-owned. Static embedding
    environment variables remain an explicit override for deployments that
    do not expose an embedding model on their provider record.
    """
    from services.settings_store import load_settings

    app_settings = await load_settings()
    active = resolve_active_provider(app_settings)
    base_url = settings.EMBEDDING_BASE_URL or active.base_url
    api_key = settings.EMBEDDING_API_KEY or active.api_key
    model = active.embedding_model or settings.EMBEDDING_MODEL or None
    return base_url, api_key, model


async def get_embeddings_from_api(texts: list[str]) -> tuple[Optional[list[list[float]]], int]:
    """Call an OpenAI-compatible embeddings endpoint.

    Returns (embeddings, total_tokens). When EMBEDDING_MODEL is empty, returns
    (None, 0) so ChromaDB falls back to its built-in default embedding model.
    """
    base_url, api_key, embedding_model = await resolve_embedding_provider()
    if not embedding_model:
        return None, 0

    if not base_url or not api_key:
        raise NotImplementedError(
            "EMBEDDING_MODEL is configured but no embeddings API endpoint is available. "
            "Set provider embedding credentials or EMBEDDING_BASE_URL/EMBEDDING_API_KEY, "
            "or clear EMBEDDING_MODEL to use ChromaDB's built-in default embedding."
        )

    validated_base_url = await asyncio.to_thread(validate_provider_base_url, base_url)
    url = validated_base_url.rstrip("/") + "/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": embedding_model, "input": texts}
    resp = await _post_embeddings(url, headers, payload)
    data = resp.json()

    embeddings = [item["embedding"] for item in data.get("data", [])]
    tokens_used = int(data.get("usage", {}).get("total_tokens", 0) or 0)
    return embeddings, tokens_used


async def log_embedding_tokens(project_id_str: str, chapter_index: int, tokens: int) -> None:
    try:
        pid = uuid.UUID(project_id_str)
        async with async_session() as session:
            usage = TokenUsage(
                project_id=pid,
                chapter_index=chapter_index,
                agent_name=AGENT_NAME_EMBEDDING,
                input_tokens=tokens,
                output_tokens=0,
                cache_hit_tokens=0,
                cache_miss_tokens=0,
                model_name=AGENT_NAME_EMBEDDING,
            )
            session.add(usage)
            await session.commit()
    except Exception:
        logger.exception("embedding_token_log_failed project_id=%s", project_id_str)
