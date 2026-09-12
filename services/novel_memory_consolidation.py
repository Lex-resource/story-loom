"""场景块摘要的整合与回退(树 B 断环:主链与支线共用同一份策略)。

整合模型路径(`ENABLE_SCENE_BLOCK_CONSOLIDATION` 开启时)与确定性回退
(大纲 summary / 正文截断)的 LLM 路径从这里出;确定性回退在 novel_memory_scenes.fallback_scene_summary——此前 knowledge_merger 与
character_branch_generation 各写一份回退表达式,导致支线永远吃不到整合。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import AGENT_SCENE_CONSOLIDATOR

logger = logging.getLogger(__name__)


async def consolidate_scene_summary(
    db: AsyncSession,
    novel: Any,
    chapter: Any,
    fallback_summary: str,
    accepted_atoms: list[Any],
) -> str:
    """用整合模型压缩场景块摘要。

    Best-effort by design: any failure or empty output returns "" so the caller
    falls back to the deterministic outline-summary / chapter-tail source.
    `novel`/`chapter` 走 duck typing(主链 Chapter 与支线 CharacterBranchChapter
    都只需 id/title/content/chapter_index 字段)。
    """
    try:
        from agents.scene_consolidator_agent import SceneConsolidatorAgent

        agent = SceneConsolidatorAgent()
        atom_statements = [
            str(getattr(atom, "statement", "") or "").strip()
            for atom in (accepted_atoms or [])
        ]
        atom_statements = [item for item in atom_statements if item][:12]
        summary = await agent.consolidate_scene_summary(
            novel_format=novel.novel_format,
            chapter_title=chapter.title or "",
            chapter_tail=(chapter.content or "")[-1500:],
            accepted_atoms=atom_statements,
            outline_summary=fallback_summary,
        )
        if summary:
            await agent.record_usage(
                db,
                novel.id,
                chapter.chapter_index,
                AGENT_SCENE_CONSOLIDATOR,
            )
        return summary
    except Exception:
        logger.exception(
            "scene_block_consolidation_failed project_id=%s chapter_index=%s",
            novel.id,
            chapter.chapter_index,
        )
        return ""
