import uuid
from typing import Optional

import httpx

from config import settings
from database import async_session
from models.novel import TokenUsage
from services.vector_constants import AGENT_NAME_EMBEDDING, EMBEDDING_TIMEOUT_SECONDS


async def get_embeddings_from_api(texts: list[str]) -> tuple[Optional[list[list[float]]], int]:
    """Call an OpenAI-compatible embeddings endpoint.

    Returns (embeddings, total_tokens). When EMBEDDING_MODEL is empty, returns
    (None, 0) so ChromaDB falls back to its built-in default embedding model.
    """
    if not settings.EMBEDDING_MODEL:
        return None, 0

    base_url = settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL
    api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
    if not base_url or not api_key:
        raise NotImplementedError(
            "EMBEDDING_MODEL is configured but no embeddings API endpoint is available. "
            "Set EMBEDDING_BASE_URL/EMBEDDING_API_KEY (or LLM_BASE_URL/LLM_API_KEY), "
            "or clear EMBEDDING_MODEL to use ChromaDB's built-in default embedding."
        )

    url = base_url.rstrip("/") + "/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": settings.EMBEDDING_MODEL, "input": texts}
    async with httpx.AsyncClient(timeout=EMBEDDING_TIMEOUT_SECONDS) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
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
    except Exception as e:
        print(f"Failed to log embedding tokens: {e}")
