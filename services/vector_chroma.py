from __future__ import annotations

import asyncio
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

try:
    import chromadb.segment.impl.metadata.sqlite as _sqlite
    _orig_decode = _sqlite._decode_seq_id

    def _patched_decode(seq_id_bytes):
        if isinstance(seq_id_bytes, int):
            return seq_id_bytes
        return _orig_decode(seq_id_bytes)

    _sqlite._decode_seq_id = _patched_decode
except Exception as _ex:
    print(f"[ChromaDB Monkeypatch WARNING] Failed to apply sqlite patch: {_ex}")

from config import settings
from services.vector_constants import VECTOR_COLLECTION_PREFIX, VECTOR_RETRIEVE_N_RESULTS
from services.vector_embeddings import get_embeddings_from_api, log_embedding_tokens

_client = None
_default_embedding_function = DefaultEmbeddingFunction()
_chroma_lock = asyncio.Lock()


def reset_chroma_state() -> None:
    global _client
    _client = None


def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    return _client


def get_or_create_collection(name: str) -> chromadb.Collection:
    client = get_client()
    if not settings.EMBEDDING_MODEL:
        return client.get_or_create_collection(name=name, embedding_function=_default_embedding_function)
    return client.get_or_create_collection(name=name)


async def run_with_chroma(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    async with _chroma_lock:
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


async def mutate_collection(
    collection_name: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    embeddings: Optional[list[list[float]]] = None,
    *,
    mode: str = "add",
) -> None:
    tokens_used = 0
    if embeddings is None and settings.EMBEDDING_MODEL:
        try:
            embeddings, tokens_used = await get_embeddings_from_api(documents)
        except NotImplementedError as exc:
            print(f"[VectorStore] {exc} Falling back to ChromaDB default embedding.")
            embeddings = None
        else:
            if tokens_used > 0 and collection_name.startswith(VECTOR_COLLECTION_PREFIX):
                project_id = collection_name.replace(VECTOR_COLLECTION_PREFIX, "")
                chapter_index = 0
                if metadatas and isinstance(metadatas, list):
                    chapter_index = metadatas[0].get("chapter_index", 0)
                await log_embedding_tokens(project_id, chapter_index, tokens_used)

    def mutate():
        collection = get_or_create_collection(collection_name)
        kwargs = {"ids": ids, "documents": documents, "metadatas": metadatas}
        if embeddings is not None:
            kwargs["embeddings"] = embeddings
        if mode == "upsert":
            collection.upsert(**kwargs)
        else:
            collection.add(**kwargs)

    await run_with_chroma(mutate)


async def add_to_collection(
    collection_name: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    embeddings: Optional[list[list[float]]] = None,
) -> None:
    await mutate_collection(collection_name, ids, documents, metadatas, embeddings, mode="add")


async def upsert_to_collection(
    collection_name: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
    embeddings: Optional[list[list[float]]] = None,
) -> None:
    await mutate_collection(collection_name, ids, documents, metadatas, embeddings, mode="upsert")


async def query_collection(
    collection_name: str,
    query_texts: list[str],
    n_results: int = VECTOR_RETRIEVE_N_RESULTS,
    where: Optional[dict] = None,
) -> dict:
    embeddings = None
    tokens_used = 0
    if settings.EMBEDDING_MODEL:
        try:
            embeddings, tokens_used = await get_embeddings_from_api(query_texts)
        except NotImplementedError as exc:
            print(f"[VectorStore] {exc} Falling back to ChromaDB default embedding.")
            embeddings = None
        else:
            if tokens_used > 0 and collection_name.startswith(VECTOR_COLLECTION_PREFIX):
                project_id = collection_name.replace(VECTOR_COLLECTION_PREFIX, "")
                await log_embedding_tokens(project_id, 0, tokens_used)

    def do_query():
        collection = get_or_create_collection(collection_name)
        kwargs = {"n_results": n_results}
        if embeddings is not None:
            kwargs["query_embeddings"] = embeddings
        else:
            kwargs["query_texts"] = query_texts
        if where:
            kwargs["where"] = where
        return collection.query(**kwargs)

    return await run_with_chroma(do_query)
