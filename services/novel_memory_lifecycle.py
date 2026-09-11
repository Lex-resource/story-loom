"""Candidate lifecycle sweep for layered novel memory.

参照 Codex memories 的 usage 淘汰（usage_count + max_unused_days）做的领域
安全弱化版：只有 ``candidate`` 态 atom 会被降级为 ``superseded``，
``accepted`` 事实绝不按频率淘汰 —— 小说里 80 章后才回收的伏笔靠
``valid_to_chapter`` 驱动（recall 的 due_atoms 路径），与命中频率无关。

"最后一次有效使用" = ``last_recalled_chapter``（召回簿记写入），没有簿记时
回退到 ``source_chapter``（写入后从未被召回过）。两值都落后当前章节超过
``idle_chapters`` 的 candidate 视为陈旧。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel_memory import NovelMemoryAtom
from services.novel_memory_types import (
    ATOM_STATUS_CANDIDATE,
    ATOM_STATUS_SUPERSEDED,
    STORYLINE_MAIN,
)

logger = logging.getLogger(__name__)

LIFECYCLE_SWEEP_SOURCE = "system:candidate_lifecycle"


async def sweep_stale_atom_candidates(
    db: AsyncSession,
    *,
    project_id: uuid.UUID,
    current_chapter: int,
    storyline_id: str = STORYLINE_MAIN,
    branch_id: uuid.UUID | None = None,
    idle_chapters: int = 12,
) -> int:
    """Supersede long-unrecalled candidate atoms; return the swept row count."""
    idle = max(1, int(idle_chapters))
    stale_before = int(current_chapter) - idle
    stmt = (
        update(NovelMemoryAtom)
        .where(
            NovelMemoryAtom.project_id == project_id,
            NovelMemoryAtom.branch_id == branch_id,
            NovelMemoryAtom.storyline_id == storyline_id,
            NovelMemoryAtom.status == ATOM_STATUS_CANDIDATE,
            func.coalesce(
                NovelMemoryAtom.last_recalled_chapter,
                NovelMemoryAtom.source_chapter,
            ) <= stale_before,
        )
        .values(status=ATOM_STATUS_SUPERSEDED)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    swept = int(result.rowcount or 0)
    if swept:
        logger.info(
            "novel_memory_candidate_sweep project_id=%s chapter_index=%s swept=%d idle_chapters=%d",
            project_id,
            current_chapter,
            swept,
            idle,
        )
    return swept
