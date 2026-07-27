"""Explicit repair operations for rebuildable storage projections."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.novel import VectorOutbox
from services.pipeline_types import VectorOutboxStatus


async def reset_replayable_vector_outbox(db: AsyncSession) -> int:
    """Return failed and expired leased rows to the pending queue."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=settings.VECTOR_OUTBOX_LEASE_SECONDS
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
