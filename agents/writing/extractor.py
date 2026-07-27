from agents.base import AgentBase, sanitize_untrusted_content, UNTRUSTED_CONTENT_SYSTEM_REMINDER, safe_format
import json

from agents.constants import (
    EXTRACTOR_TEMPERATURE,
    NOVEL_FORMAT_LONG_WEBNOVEL,
    PROMPT_EXTRACTOR_EXTRACT_CHANGES,
    PROMPT_EXTRACTOR_SUMMARIZE_CHANGES,
)
from agents.pipeline_context import PipelineContext
from agents.writing_schemas import ExtractorChangeCandidates


class ExtractorAgent(AgentBase):
    def __init__(self):
        super().__init__()  # 使用 config 中的模型

    async def extract_changes(
        self,
        context: PipelineContext,
    ) -> dict:
        chapter_content = context.chapter_content
        world_state = context.world_state
        character_state = context.character_state
        foreshadowing = context.foreshadowing
        plot_threads = context.plot_threads
        chapter_index = context.chapter_index
        novel_format = context.novel_format

        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_EXTRACTOR_EXTRACT_CHANGES,
            category=novel_format
        )

        change_candidates = ""
        if novel_format == NOVEL_FORMAT_LONG_WEBNOVEL:
            candidates = await self.summarize_change_candidates(context)
            change_candidates = json.dumps(candidates, ensure_ascii=False, indent=2)

        sys_prompt = safe_format(system_tmpl, chapter_index=chapter_index) + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            world_state=sanitize_untrusted_content(world_state),
            character_state=sanitize_untrusted_content(character_state),
            foreshadowing=sanitize_untrusted_content(foreshadowing),
            plot_threads=sanitize_untrusted_content(plot_threads),
            chapter_content=sanitize_untrusted_content(chapter_content),
            chapter_index=chapter_index,
            change_candidates=sanitize_untrusted_content(change_candidates),
        )

        # 延迟 import 以避免 agents → services 反向依赖
        from services.knowledge_patch_models import KnowledgePatchSet

        return await self.call_llm_json(
            sys_prompt, user_prompt, temperature=EXTRACTOR_TEMPERATURE,
            response_schema=KnowledgePatchSet
        )

    async def summarize_change_candidates(self, context: PipelineContext) -> dict:
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_EXTRACTOR_SUMMARIZE_CHANGES,
            category=context.novel_format,
        )
        sys_prompt = safe_format(
            system_tmpl,
            chapter_index=context.chapter_index,
        ) + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            world_state=sanitize_untrusted_content(context.world_state),
            character_state=sanitize_untrusted_content(context.character_state),
            foreshadowing=sanitize_untrusted_content(context.foreshadowing),
            plot_threads=sanitize_untrusted_content(context.plot_threads),
            chapter_content=sanitize_untrusted_content(context.chapter_content),
            chapter_index=context.chapter_index,
        )
        return await self.call_llm_json(
            sys_prompt,
            user_prompt,
            temperature=EXTRACTOR_TEMPERATURE,
            response_schema=ExtractorChangeCandidates,
        )

