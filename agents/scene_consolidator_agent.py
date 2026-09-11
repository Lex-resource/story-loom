"""Scene-block consolidation agent（记忆整合，参照 Codex memories 的双模型分离）.

Extractor 负责从章节正文提取结构化候选（Phase 1）；本 agent 只负责把已确认
的章节事实压缩成场景块摘要（Phase 2）。两者分离后，整合可以走
``CONSOLIDATION_MODEL`` 指定的便宜模型 —— 整合是纯压缩改写，不需要主力模型。

失败永远不阻塞章节发布：调用方（knowledge_merger）拿到异常或空摘要时回退到
确定性的大纲 summary / 正文截断来源。
"""

from __future__ import annotations

import logging

from agents.base import (
    AgentBase,
    UNTRUSTED_CONTENT_SYSTEM_REMINDER,
    safe_format,
    sanitize_untrusted_content,
)
from agents.constants import (
    CONSOLIDATION_TEMPERATURE,
    PROMPT_SCENE_BLOCK_CONSOLIDATION,
)
from agents.writing_schemas import SceneBlockConsolidation

logger = logging.getLogger(__name__)


class SceneConsolidatorAgent(AgentBase):
    """Compress accepted chapter facts into one scene-block summary."""

    def __init__(self):
        from config import settings

        super().__init__(model=settings.CONSOLIDATION_MODEL or None)

    async def consolidate_scene_summary(
        self,
        *,
        novel_format: str,
        chapter_title: str,
        chapter_tail: str,
        accepted_atoms: list[str],
        outline_summary: str,
    ) -> str:
        """Return one compressed summary string; empty string means fall back."""
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_SCENE_BLOCK_CONSOLIDATION,
            category=novel_format,
        )
        sys_prompt = safe_format(system_tmpl) + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            chapter_title=chapter_title,
            chapter_tail=sanitize_untrusted_content(chapter_tail),
            accepted_atoms=sanitize_untrusted_content(
                "\n".join(f"- {item}" for item in accepted_atoms) or "（无）"
            ),
            outline_summary=sanitize_untrusted_content(outline_summary or "（无）"),
        )
        result = await self.call_llm_json(
            sys_prompt,
            user_prompt,
            temperature=CONSOLIDATION_TEMPERATURE,
            response_schema=SceneBlockConsolidation,
        )
        summary = ""
        if isinstance(result, dict):
            summary = str(result.get("summary") or "").strip()
        if not summary:
            logger.warning("scene_block_consolidation_empty_summary")
        return summary
