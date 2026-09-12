"""向量索引外发队列后台轮询。

从 VectorOutbox 表中取出 PENDING 记录，将 payload 中的 items 写入向量库。
失败的记录累加 retry_count，达到上限后转为 FAILED。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import delete, select, update

from database import async_session
from models.character_branches import CharacterBranch
from models.novel import VectorOutbox
from services.character_constants import (
    CHARACTER_BRANCH_STATUS_ARCHIVED,
    CHARACTER_BRANCH_VECTOR_COLLECTION_PREFIX,
)
from services.pipeline_types import VectorOutboxStatus
from services.runtime_tunables_service import get_value
from services.vector_constants import (
    VECTOR_CHAPTER_ITEM_ID_TEMPLATE,
    VECTOR_COLLECTION_PREFIX,
    VECTOR_SOURCE_CHAPTER_EXTRACT,
    VECTOR_UNKNOWN_CHAPTER_INDEX,
    VECTOR_UNKNOWN_ITEM_TYPE,
)
from services.vector_chroma import upsert_to_collection

logger = logging.getLogger(__name__)


async def cleanup_done_outboxes(retention_seconds: int | None = None) -> int:
    """分批删除超过保留期的 DONE 行，返回删除总数。

    保留期与单批上限入库（runtime_tunables），每次清理时读取；分批短事务
    是为了避免长事务阻塞 outbox 写入。
    """
    total = 0
    try:
        if retention_seconds is None:
            retention_seconds = await get_value("vector_outbox_done_retention_seconds")
        purge_batch = await get_value("vector_outbox_purge_batch")
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            seconds=retention_seconds
        )
        while True:
            async with async_session() as db:
                batch_ids = (
                    select(VectorOutbox.id)
                    .where(
                        VectorOutbox.status == VectorOutboxStatus.DONE,
                        VectorOutbox.updated_at < cutoff,
                    )
                    .order_by(VectorOutbox.updated_at)
                    .limit(purge_batch)
                )
                result = await db.execute(
                    delete(VectorOutbox).where(VectorOutbox.id.in_(batch_ids))
                )
                await db.commit()
            deleted = result.rowcount or 0
            total += deleted
            if deleted < purge_batch:
                break
        if total:
            logger.info("vector_outbox_done_rows_purged count=%s", total)
        return total
    except Exception:
        logger.exception("vector_outbox_done_cleanup_failed")
        return total


async def _recover_orphaned_syncing() -> None:
    """将残留的 SYNCING 行回退为 PENDING。

    SYNCING 是本循环内的瞬间态；若进程在写向量库中途崩溃/重启，行会永久停在
    SYNCING，而轮询只捞 PENDING，导致该条目再不会被同步（DB 与向量库不一致）。
    启动时一次性回收这些孤儿。add_to_collection 的 id 是确定性的（chapter/type/name），
    重放至多是幂等 upsert，安全。
    """
    try:
        lease_seconds = await get_value("vector_outbox_lease_seconds")
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            seconds=lease_seconds
        )
        async with async_session() as db:
            await db.execute(
                update(VectorOutbox)
                .where(
                    VectorOutbox.status == VectorOutboxStatus.SYNCING,
                    VectorOutbox.updated_at < cutoff,
                )
                .values(status=VectorOutboxStatus.PENDING)
            )
            await db.commit()
    except Exception:
        logger.exception("vector_outbox_lease_recovery_failed")


async def claim_vector_outboxes(limit: int = 10) -> list[uuid.UUID]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with async_session() as db:
        async with db.begin():
            result = await db.execute(
                select(VectorOutbox)
                .where(VectorOutbox.status == VectorOutboxStatus.PENDING)
                .order_by(VectorOutbox.created_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
            outboxes = result.scalars().all()
            for outbox in outboxes:
                outbox.status = VectorOutboxStatus.SYNCING
                outbox.updated_at = now
            return [outbox.id for outbox in outboxes]


async def process_vector_outbox(outbox_id: uuid.UUID) -> None:
    async with async_session() as db:
        outbox = await db.get(VectorOutbox, outbox_id)
        if not outbox or outbox.status != VectorOutboxStatus.SYNCING:
            return
        payload = outbox.payload or {}
        collection_name = str(payload.get("collection_name") or "")
        if collection_name.startswith(CHARACTER_BRANCH_VECTOR_COLLECTION_PREFIX):
            try:
                branch_id = uuid.UUID(
                    collection_name[len(CHARACTER_BRANCH_VECTOR_COLLECTION_PREFIX):]
                )
            except ValueError:
                branch_id = None
            if branch_id is not None:
                branch = (await db.execute(
                    select(CharacterBranch)
                    .where(CharacterBranch.id == branch_id)
                    .with_for_update()
                )).scalar_one_or_none()
                # Re-read after taking the branch lock.  Archive either
                # deleted the row or committed archived state while this item
                # was waiting for the lock.
                outbox = await db.get(VectorOutbox, outbox_id)
                if not outbox or outbox.status != VectorOutboxStatus.SYNCING:
                    return
                if branch is None or branch.status == CHARACTER_BRANCH_STATUS_ARCHIVED:
                    await db.delete(outbox)
                    await db.commit()
                    return
        try:
            items = outbox.payload.get("items", [])
            for item in items:
                item_type = str(item.get("type") or VECTOR_UNKNOWN_ITEM_TYPE)
                name = str(item.get("name") or "")
                item_id = str(
                    item.get("id")
                    or VECTOR_CHAPTER_ITEM_ID_TEMPLATE.format(
                        chapter_index=outbox.chapter_index,
                        item_type=item_type,
                        name=name,
                    )
                )
                desc = str(item.get("description") or item.get("text") or "")
                source = str(item.get("source") or VECTOR_SOURCE_CHAPTER_EXTRACT)
                metadata = {
                    "source": source,
                    "type": item_type,
                    "name": name,
                    "chapter_index": outbox.chapter_index or VECTOR_UNKNOWN_CHAPTER_INDEX,
                }
                if isinstance(item.get("metadata"), dict):
                    metadata.update(item["metadata"])
                collection_name = str(
                    (outbox.payload or {}).get("collection_name")
                    or f"{VECTOR_COLLECTION_PREFIX}{outbox.project_id}"
                )
                await upsert_to_collection(
                    collection_name=collection_name,
                    ids=[item_id],
                    documents=[desc],
                    metadatas=[metadata],
                )
            outbox.status = VectorOutboxStatus.DONE
            outbox.error = None
        except Exception as e:
            logger.exception("vector_outbox_processing_failed outbox_id=%s", outbox_id)
            outbox.retry_count = (outbox.retry_count or 0) + 1
            outbox.error = str(e)
            outbox.status = (
                VectorOutboxStatus.FAILED
                if outbox.retry_count >= (outbox.max_retries or 3)
                else VectorOutboxStatus.PENDING
            )
        await db.commit()


async def poll_vector_outbox() -> None:
    """循环轮询 VectorOutbox 表，将 pending 项同步到向量库。"""
    await _recover_orphaned_syncing()
    last_done_cleanup = 0.0
    while True:
        outbox_ids = await claim_vector_outboxes(10)
        for outbox_id in outbox_ids:
            await process_vector_outbox(outbox_id)
        # 清理间隔与轮询间隔每次迭代读取,前端改完下一轮生效
        cleanup_interval = await get_value("vector_outbox_done_cleanup_interval_seconds")
        if time.monotonic() - last_done_cleanup >= cleanup_interval:
            last_done_cleanup = time.monotonic()
            await cleanup_done_outboxes()
        await asyncio.sleep(await get_value("worker_poll_interval_seconds"))
