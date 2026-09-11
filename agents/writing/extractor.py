from agents.base import AgentBase, sanitize_untrusted_content, UNTRUSTED_CONTENT_SYSTEM_REMINDER, safe_format
import json

from agents.constants import (
    EXTRACTOR_TEMPERATURE,
    PROMPT_EXTRACTOR_EXTRACT_CHANGES,
    PROMPT_EXTRACTOR_SUMMARIZE_CHANGES,
    PROMPT_EXTRACT_CHARACTER_CARDS,
    CHARACTER_FACT_SOURCE_RULES,
    CHARACTER_CARD_EXTRACTION_RULES,
)
from agents.pipeline_context import PipelineContext
from agents.prompt_hints import (
    authority_boundary_hint,
    agent_context_policy,
    continuity_contract_hint,
    continuity_handoff_hint,
    generation_hints as agent_generation_hints,
    narrative_index_hint,
    novel_memory_hint,
    repair_surface_hints,
    v42_authority_locked_progression_hint,
    v43_bounded_hypothesis_progression_hint,
)
from agents.writing_schemas import ExtractorChangeCandidates
from services.character_types import CharacterCardExtractionResponse
from services.workflow_surface import is_short_form_workflow


import logging

logger = logging.getLogger(__name__)


class ExtractorAgent(AgentBase):
    def __init__(self):
        super().__init__()  # 使用 config 中的模型

    async def extract_changes(
        self,
        context: PipelineContext,
    ) -> dict:
        # 交接包与章节契约的原始副本按表面策略决定（短篇不收）—— 与 Editor/Validator 同款。
        if agent_context_policy("extractor", context.novel_format)["suppress_handoff_and_contract"]:
            context.chapter_handoff_context = ""
            context.chapter_contract_context = ""
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
        # 变更候选摘要按**表面策略**决定，不按格式名：克隆自长篇的自定义工作流同样需要它，
        # 否则 `change_candidates` 恒空，Extractor 少一整块输入而没有任何报错。
        if not is_short_form_workflow(novel_format):
            candidates = await self.summarize_change_candidates(context)
            change_candidates = json.dumps(candidates, ensure_ascii=False, indent=2)

        generation_hints = agent_generation_hints("extractor", novel_format)
        sys_prompt = safe_format(system_tmpl, chapter_index=chapter_index) + authority_boundary_hint() + generation_hints + UNTRUSTED_CONTENT_SYSTEM_REMINDER
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
        user_prompt += novel_memory_hint(context.novel_memory_context, "extractor")
        user_prompt += continuity_handoff_hint(context.chapter_handoff_context)
        user_prompt += continuity_contract_hint(context.chapter_contract_context)
        user_prompt += narrative_index_hint(context.narrative_index_context, "extractor")

        # 延迟 import 以避免 agents → services 反向依赖
        from services.knowledge_patch_models import KnowledgePatchSet

        result = await self.call_llm_json(
            sys_prompt, user_prompt, temperature=EXTRACTOR_TEMPERATURE,
            response_schema=KnowledgePatchSet
        )
        if context.character_card_context:
            try:
                result["character_updates"] = await self.extract_character_updates(context)
            except Exception as exc:
                logger.warning(f"[ExtractorAgent] character card extraction skipped: {exc}")
        return result

    async def extract_character_updates(self, context: PipelineContext) -> list[dict]:
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_EXTRACT_CHARACTER_CARDS,
            category=context.novel_format,
        )
        sys_prompt = safe_format(
            system_tmpl,
            chapter_index=context.chapter_index,
        ) + (
            authority_boundary_hint()
            + (
                repair_surface_hints("extractor")
            )
            + CHARACTER_FACT_SOURCE_RULES
            + CHARACTER_CARD_EXTRACTION_RULES
            + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        )
        user_prompt = safe_format(
            user_tmpl,
            chapter_index=context.chapter_index,
            character_card_context=sanitize_untrusted_content(context.character_card_context),
            chapter_content=sanitize_untrusted_content(context.chapter_content),
        )
        response = await self.call_llm_json(
            sys_prompt,
            user_prompt,
            temperature=EXTRACTOR_TEMPERATURE,
            response_schema=CharacterCardExtractionResponse,
        )
        return response.get("updates", []) if isinstance(response, dict) else []

    async def summarize_change_candidates(self, context: PipelineContext) -> dict:
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_EXTRACTOR_SUMMARIZE_CHANGES,
            category=context.novel_format,
        )
        sys_prompt = safe_format(
            system_tmpl,
            chapter_index=context.chapter_index,
        ) + (
            authority_boundary_hint()
            + (
                repair_surface_hints("extractor")
            )
            + v43_bounded_hypothesis_progression_hint("extractor")
            + v42_authority_locked_progression_hint("extractor")
            + CHARACTER_FACT_SOURCE_RULES
            + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        )
        user_prompt = safe_format(
            user_tmpl,
            world_state=sanitize_untrusted_content(context.world_state),
            character_state=sanitize_untrusted_content(context.character_state),
            foreshadowing=sanitize_untrusted_content(context.foreshadowing),
            plot_threads=sanitize_untrusted_content(context.plot_threads),
            chapter_content=sanitize_untrusted_content(context.chapter_content),
            chapter_index=context.chapter_index,
        )
        user_prompt += narrative_index_hint(context.narrative_index_context, "extractor")
        return await self.call_llm_json(
            sys_prompt,
            user_prompt,
            temperature=EXTRACTOR_TEMPERATURE,
            response_schema=ExtractorChangeCandidates,
        )

