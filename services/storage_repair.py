"""Explicit repair operations for rebuildable storage projections."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel import VectorOutbox
from services.pipeline_types import VectorOutboxStatus
from services.runtime_tunables_service import get_value


async def reset_replayable_vector_outbox(db: AsyncSession) -> int:
    """Return failed and expired leased rows to the pending queue.

    租约时长与 worker 侧同源（runtime_tunables 的 vector_outbox_lease_seconds），
    避免修复路径还读静态 env 值造成两处分叉。
    """
    lease_seconds = await get_value("vector_outbox_lease_seconds")
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=lease_seconds
    )
    result = await db.execute(
        update(VectorOutbox)
        .where(
            (VectorOutbox.status == VectorOutboxStatus.FAILED)
            | (
                (VectorOutbox.status == VectorOutboxStatus.SYNCING)
                & (VectorOutbox.updated_at < cutoff)
            )
        )
        .values(
            status=VectorOutboxStatus.PENDING,
            retry_count=0,
            error=None,
        )
    )
    await db.commit()
    return int(result.rowcount or 0)
