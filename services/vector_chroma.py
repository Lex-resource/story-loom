from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

import chromadb
from chromadb.errors import InvalidCollectionException
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

logger = logging.getLogger(__name__)

try:
    import chromadb.segment.impl.metadata.sqlite as _sqlite
    _orig_decode = _sqlite._decode_seq_id

    def _patched_decode(seq_id_bytes):
        if isinstance(seq_id_bytes, int):
            return seq_id_bytes
        return _orig_decode(seq_id_bytes)

    _sqlite._decode_seq_id = _patched_decode
except Exception:
    logger.warning("chroma_sqlite_seq_id_patch_failed", exc_info=True)

from config import settings
from services.runtime_tunables_service import get_value
from services.vector_constants import VECTOR_COLLECTION_PREFIX, VECTOR_RETRIEVE_N_RESULTS
from services.vector_embeddings import get_embeddings_from_api, log_embedding_tokens

_client = None
_default_embedding_function = DefaultEmbeddingFunction()
_chroma_lock = asyncio.Lock()


def reset_chroma_state() -> None:
    global _client
    _client = None


# chroma 启动预热的结果健康标志:True=读写探针通过。None=尚未预热。
chroma_warmup_ok: Optional[bool] = None

# chromadb 0.5.0 硬编码的 ONNX 兜底模型缓存目录(无重定向钩子)。
_ONNX_MODEL_CACHE_DIR = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2"


def preload_chroma() -> bool:
    """启动预热：把最大挂死源移出热路径，并自检 chroma 读写可用。

    三件事（仿 preload_tokenizer，在 lifespan/worker 的 to_thread 里跑）：
    1. 打开 client + collection（触发 System 组装、内部 SQLite 打开）；
    2. 读写探针：自检集合 upsert 1 条（显式 embeddings，免 API/模型依赖）
       → query 1 次 → 删文档，探针集合本身也在 finally 里删除（含失败残留），
       不留一个永远为空的集合躺在集合列表里 —— 对齐"写路径必须成功"的验收；
    3. embedding 兜底预热：模型已在缓存时强制加载/建立会话（首次 query_texts
       兜底的最大延迟来源）。模型缺缓存时**不**在这里触发下载 —— 0.5.0 的
       下载 requests.get 不带 timeout，离线/半开连接会无限挂，改为明确告警，
       让运维在启动期就看到"兜底召回不可用"，而不是等 120s 僵尸。

    失败不抛：记日志并置健康标志，chroma 照常可用（召回按"异常→空记忆"降级）。
    """
    global chroma_warmup_ok
    ok = True
    # 探针集合名带 pid:外部 worker 模式下 API 与 worker 几乎同时预热,共享名
    # 会让一方的 delete_collection 撞翻另一方进行中的探针(误报 health failed)。
    # 极端情况(进程在探针中途崩溃)会残留一个空集合,名字自解释且不累积。
    probe_name = f"chroma_warmup_probe_{os.getpid()}"
    try:
        collection = get_or_create_collection(probe_name)
        probe_vec = [0.0] * 384  # all-MiniLM-L6-v2 维度
        collection.upsert(
            ids=["warmup-probe"],
            documents=["warmup"],
            embeddings=[probe_vec],
            metadatas=[{"source": "warmup"}],
        )
        res = collection.query(query_embeddings=[probe_vec], n_results=1)
        if not res.get("ids") or "warmup-probe" not in (res["ids"] or [[]])[0]:
            raise RuntimeError(f"warmup probe query missed: {res!r}")
        collection.delete(ids=["warmup-probe"])
        logger.info("chroma_warmup_probe_ok")
    except Exception:
        logger.exception("chroma_warmup_probe_failed")
        ok = False
    finally:
        # 探针集合用完即删:get_or_create 会复用所以不累积,但留着就是一个
        # 永远为空的集合,一直躺在集合列表里污染枚举视图。清理失败只记 debug
        # —— 它不影响"读写可用"的探针结论。
        try:
            get_client().delete_collection(probe_name)
        except Exception:
            logger.debug("chroma_warmup_probe_collection_cleanup_skipped")

    try:
        if _ONNX_MODEL_CACHE_DIR.exists():
            _default_embedding_function(["warmup"])
            logger.info("chroma_embedding_warmup_ok")
        else:
            logger.warning(
                "chroma_embedding_model_cache_missing path=%s "
                "impact=query_texts 兜底召回不可用(首次调用会触发无超时下载,离线环境会挂)",
                str(_ONNX_MODEL_CACHE_DIR),
            )
    except Exception:
        logger.exception("chroma_embedding_warmup_failed")

    chroma_warmup_ok = ok
    return ok


def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
    return _client


def get_or_create_collection(name: str) -> chromadb.Collection:
    client = get_client()
    # The active provider and its embedding model live in PostgreSQL, so the
    # static environment flag cannot decide which embedding function to use.
    # Supplying the local function is harmless when explicit API embeddings are
    # passed, and keeps the fallback deterministic when no model is configured.
    return client.get_or_create_collection(name=name, embedding_function=_default_embedding_function)


def _sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, str | int | float | bool]:
    """Convert metadata to Chroma's scalar-only format.

    Extractor payloads commonly contain optional ``None`` values and nested
    lists. Chroma rejects both, so omit nulls and serialize structured values
    deterministically before writing the vector record.
    """
    sanitized: dict[str, str | int | float | bool] = {}
    for key, value in (metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            sanitized[str(key)] = value
        else:
            sanitized[str(key)] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return sanitized


def _sanitize_metadatas(metadatas: list[dict] | None) -> list[dict[str, str | int | float | bool]]:
    return [_sanitize_metadata(metadata) for metadata in (metadatas or [])]


# 专用单线程 executor：默认池是多线程的，wait_for 超时释放锁后，下一个操作
# 会在**另一条线程**上与僵尸并发争抢 chroma 内部 SQLite 锁。所有 chroma 操作
# 走同一条单线程队列即天然串行，僵尸不再有并发对象；僵尸被检出后整个线程池
# 被隔离重建（见 finally）。超时/阈值入库（runtime_tunables），每次调用读取。
# 注意 wait_for 超时无法取消已在 executor 线程里跑的 chroma 调用，只能止损。
_chroma_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="chroma")

# 当前正在 executor 线程里执行的任务的开始时刻（None=线程空闲）。
# 僵尸占用期 = now - _op_started_at：挂死操作把单线程占住时，后续每个排队
# 操作超时都看同一个起点，占用期随之增长，越过阈值即触发隔离重建。
_op_started_at: Optional[float] = None
# executor 代际：每次重建 +1。先前超时调用的孤儿 lambda 会在旧线程延迟执行
# 完毕，其 tracked 收尾不得触碰新一代的状态（否则会抹掉当前任务的起点，
# 推迟下一次僵尸检出）。
_executor_generation: int = 0


class ChromaTimeoutError(TimeoutError):
    """chroma 操作超时。"""


class ChromaZombieIsolatedError(ChromaTimeoutError):
    """超时且僵尸线程已被隔离（executor 已换新）—— 新线程上重试大概率立即成功。"""


def _run_tracked(token: int, func, *args, **kwargs):
    """executor 线程内的包装：记录任务开始执行的时刻，供僵尸占用期判定。

    带提交时的代际标记：被隔离重建后，旧代的孤儿任务（超时调用的 lambda
    在旧线程里延迟跑完）不再读写当前代的状态。
    """
    global _op_started_at
    if token != _executor_generation:
        return func(*args, **kwargs)
    _op_started_at = time.monotonic()
    try:
        return func(*args, **kwargs)
    finally:
        if token == _executor_generation:
            _op_started_at = None


async def run_with_chroma(func, *args, **kwargs):
    global _chroma_executor, _op_started_at, _executor_generation
    loop = asyncio.get_running_loop()
    lock_timeout = await get_value("chroma_lock_acquire_timeout_seconds")
    operation_timeout = await get_value("chroma_operation_timeout_seconds")
    zombie_threshold = await get_value("chroma_zombie_threshold_seconds")
    try:
        await asyncio.wait_for(_chroma_lock.acquire(), timeout=lock_timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(
            f"chroma lock acquire timed out after {lock_timeout}s"
        )
    generation = _executor_generation
    started = time.monotonic()
    timed_out = False
    recycled = False
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                _chroma_executor, lambda: _run_tracked(generation, func, *args, **kwargs)
            ),
            timeout=operation_timeout,
        )
    except asyncio.TimeoutError:
        timed_out = True
    finally:
        if timed_out:
            # 占用期优先看线程侧起点：挂死操作把单线程占住时，每个后续排队
            # 操作的超时都共享同一个起点，占用期单调增长。无起点信息时退回
            # 本次调用耗时。
            now = time.monotonic()
            # 先取局部快照再判空:executor 线程可能恰在判 None 与减法两条
            # 字节码之间把它置 None,裸读会以 TypeError 换掉本应抛的超时异常。
            op_started = _op_started_at
            occupancy = (now - op_started) if op_started is not None else (now - started)
            if occupancy > zombie_threshold:
                # shutdown(wait=False) 不等僵尸结束 —— 旧线程被隔离后自生自灭，
                # 新线程立即接活；不重建 client（0.5.0 的 PersistentClient 是
                # 进程级单例，重建是空操作）。提交侧无排队任务（全局锁保证同一
                # 时刻只有一个操作被 submit）；唯一残留是刚才这个超时调用的
                # 孤儿 lambda，代际标记让它延迟跑完时不再触碰新一代状态。
                stale = _chroma_executor
                _chroma_executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="chroma"
                )
                stale.shutdown(wait=False)
                _executor_generation += 1
                _op_started_at = None
                recycled = True
                logger.warning(
                    "chroma_executor_recycled occupancy_seconds=%.1f threshold_seconds=%.1f",
                    occupancy,
                    zombie_threshold,
                )
        _chroma_lock.release()
    if timed_out:
        if recycled:
            raise ChromaZombieIsolatedError(
                f"chroma operation timed out after {operation_timeout}s (executor recycled)"
            )
        raise ChromaTimeoutError(
            f"chroma operation timed out after {operation_timeout}s"
        )


async def has_collection_documents(collection_name: str) -> bool:
    """Check an existing collection without initializing an embedding model."""
    def inspect_collection() -> bool:
        try:
            collection = get_client().get_collection(collection_name)
        except Exception:
            return False
        return bool(collection.count())

    return await run_with_chroma(inspect_collection)


async def delete_collection(collection_name: str) -> None:
    """Delete a rebuildable collection, tolerating an absent namespace."""
    def remove() -> None:
        try:
            get_client().delete_collection(name=collection_name)
        except InvalidCollectionException:
            # A project may never have written vectors, so absence is normal.
            return

    await run_with_chroma(remove)


async def delete_collection_items(collection_name: str, ids: list[str]) -> None:
    """Delete known projected records without recreating a collection."""
    if not ids:
        return

    def remove_items() -> None:
        try:
            get_client().get_collection(collection_name).delete(ids=ids)
        except InvalidCollectionException:
            # The collection or record may not have been projected yet.
            return

    await run_with_chroma(remove_items)


async def delete_collection_where(collection_name: str, where: dict) -> None:
    """Delete projected records matching metadata without creating a collection."""
    if not where:
        return

    def remove_matching() -> None:
        try:
            get_client().get_collection(collection_name).delete(where=where)
        except InvalidCollectionException:
            # The collection may not exist for a project with no vector writes.
            return

    await run_with_chroma(remove_matching)


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
    # The active provider is database-backed, so this must not depend only on
    # the legacy static EMBEDDING_MODEL environment variable.
    if embeddings is None:
        try:
            embeddings, tokens_used = await get_embeddings_from_api(documents)
        except NotImplementedError as exc:
            logger.warning("embedding_api_unavailable fallback=chroma_default error=%s", exc)
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
        kwargs = {"ids": ids, "documents": documents, "metadatas": _sanitize_metadatas(metadatas)}
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
    # Resolve the dynamic provider here as well as for writes. If it has no
    # embedding model, get_embeddings_from_api returns None and Chroma's local
    # embedding function remains the fallback.
    try:
        embeddings, tokens_used = await get_embeddings_from_api(query_texts)
    except NotImplementedError as exc:
        logger.warning("embedding_api_unavailable fallback=chroma_default error=%s", exc)
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

    try:
        return await run_with_chroma(do_query)
    except ChromaZombieIsolatedError:
        # 召回是读路径:僵尸线程刚被隔离(executor 已换新),立即在新线程重试
        # 一次,把"一次挂死"从召回失败降级成一次额外等待;若重试仍超时(磁盘级
        # hang),照常抛给调用方走空记忆降级。普通超时(executor 未隔离)不重试
        # ——线程仍被占用,重试只会再排一次队。
        logger.warning("chroma_query_timeout_retry_once")
        return await run_with_chroma(do_query)
