"""向量索引外发队列后台轮询。

从 VectorOutbox 表中取出 PENDING 记录，将 payload 中的 items 写入向量库。
失败的记录累加 retry_count，达到上限后转为 FAILED。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select, update

from config import settings
from database import async_session
from models.novel import VectorOutbox
from services.pipeline_types import VectorOutboxStatus
from services.vector_store import upsert_to_collection

logger = logging.getLogger(__name__)


async def _recover_orphaned_syncing() -> None:
    """将残留的 SYNCING 行回退为 PENDING。

    SYNCING 是本循环内的瞬间态；若进程在写向量库中途崩溃/重启，行会永久停在
    SYNCING，而轮询只捞 PENDING，导致该条目再不会被同步（DB 与向量库不一致）。
    启动时一次性回收这些孤儿。add_to_collection 的 id 是确定性的（chapter/type/name），
    重放至多是幂等 upsert，安全。
    """
    try:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            seconds=settings.VECTOR_OUTBOX_LEASE_SECONDS
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
        try:
            items = outbox.payload.get("items", [])
            for item in items:
                item_type = item.get("type", "unknown")
                name = item.get("name", "")
                desc = item.get("description", "")
                await upsert_to_collection(
                    collection_name=f"project_{outbox.project_id}",
                    ids=[f"{outbox.chapter_index}_{item_type}_{name}"],
                    documents=[desc],
                    metadatas=[{
                        "source": "chapter_extract",
                        "type": item_type,
                        "name": name,
                        "chapter_index": outbox.chapter_index or 0,
                    }],
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
    while True:
        outbox_ids = await claim_vector_outboxes(10)
        for outbox_id in outbox_ids:
            await process_vector_outbox(outbox_id)
        await asyncio.sleep(settings.WORKER_POLL_INTERVAL)
