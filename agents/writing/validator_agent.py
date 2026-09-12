import json

from agents.base import AgentBase, sanitize_untrusted_content, UNTRUSTED_CONTENT_SYSTEM_REMINDER, safe_format
from agents.pipeline_context import PipelineContext
from agents.writing_schemas import ValidatorResponse
from agents.constants import (
    VALIDATOR_TEMPERATURE,
    VALIDATOR_EXTRACT_TEMPERATURE,
    PROMPT_VALIDATOR_VALIDATE_CONTENT,
    PROMPT_VALIDATOR_REVIEW_FULL_STORY,
    PROMPT_VALIDATOR_EXTRACT_ENTITIES,
    VALIDATOR_MAX_TOKENS,
    CHARACTER_FACT_SOURCE_RULES,
)
from agents.prompt_hints import (
    agent_context_policy,
    authority_boundary_hint,
    compact_layered_prompt,
    continuity_contract_hint,
    continuity_handoff_hint,
    generation_hints as agent_generation_hints,
    narrative_index_hint,
    novel_memory_hint,
    previous_ending_for_prompt,
    validator_extra_requirements,
    validator_trailing_hint,
)
from services.continuity_contract import prompt_outline_for_agent


import logging

logger = logging.getLogger(__name__)


class ValidatorAgent(AgentBase):
    def __init__(self):
        super().__init__()

    async def validate_content(
        self,
        context: PipelineContext,
        on_chunk = None,
    ) -> dict:
        # 交接包与章节契约的原始副本按表面策略决定（短篇不收）。清掉后
        # `previous_ending_for_prompt` 会回落到完整的上一节结尾，正是短篇要的形状。
        if agent_context_policy("validator", context.novel_format)["suppress_handoff_and_contract"]:
            context.chapter_handoff_context = ""
            context.chapter_contract_context = ""
        title = context.title
        content = context.chapter_content
        active_entities_context = "\n".join(filter(None, [
            f"【短篇已写全文】\n{sanitize_untrusted_content(context.full_manuscript_context)}" if context.full_manuscript_context else None,
            f"【全局状态】\n{sanitize_untrusted_content(context.world_state)}" if context.world_state else None,
            f"【人物状态】\n{sanitize_untrusted_content(context.character_state)}" if context.character_state else None,
            f"【伏笔账本】\n{sanitize_untrusted_content(context.foreshadowing)}" if context.foreshadowing else None,
            f"【主线进度】\n{sanitize_untrusted_content(context.plot_threads)}" if context.plot_threads else None,
            f"【角色卡事实约束】\n{sanitize_untrusted_content(context.character_card_context)}" if context.character_card_context else None,
            novel_memory_hint(context.novel_memory_context, "validator"),
            continuity_handoff_hint(context.chapter_handoff_context),
            continuity_contract_hint(context.chapter_contract_context),
            narrative_index_hint(context.narrative_index_context, "validator"),
                f"【本章单章大纲】\n{sanitize_untrusted_content(json.dumps(prompt_outline_for_agent(context.chapter_outline, agent_type='validator'), ensure_ascii=False))}"
                if context.chapter_outline else None,
        ]))
        previous_ending = previous_ending_for_prompt(
            context.previous_ending,
            context.chapter_handoff_context,
        )
        novel_format = context.novel_format
        genre = context.genre
        style = context.style

        try:
            system_tmpl, user_tmpl = await self.get_prompt_template(
                PROMPT_VALIDATOR_VALIDATE_CONTENT,
                category=novel_format
            )

            generation_hints = agent_generation_hints("validator", novel_format)
            sys_prompt = system_tmpl + authority_boundary_hint() + generation_hints + CHARACTER_FACT_SOURCE_RULES + validator_extra_requirements(novel_format) + UNTRUSTED_CONTENT_SYSTEM_REMINDER
            sys_prompt += validator_trailing_hint(novel_format)
            user_prompt = safe_format(
                user_tmpl,
                title=title,
                genre=genre,
                style=style,
                content=sanitize_untrusted_content(content),
                active_entities_context=active_entities_context,
                global_outline=context.global_outline,
                short_term_context=active_entities_context,
                previous_ending=sanitize_untrusted_content(previous_ending),
                full_manuscript_context=sanitize_untrusted_content(context.full_manuscript_context),
            )
            user_prompt = compact_layered_prompt(user_prompt)

            res = await self.call_llm_json(
                sys_prompt, user_prompt, temperature=VALIDATOR_TEMPERATURE, max_tokens=VALIDATOR_MAX_TOKENS, on_chunk=on_chunk,
                response_schema=ValidatorResponse
            )
            return res
        except Exception as e:
            logger.error(f"[ValidatorAgent ERROR] LLM analysis failed: {e}")
            raise RuntimeError(f"Validator validation failed: {e}")

    async def extract_entities(self, content: str, novel_format: str) -> list[str]:
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_VALIDATOR_EXTRACT_ENTITIES,
            category=novel_format
        )

        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(user_tmpl, content=sanitize_untrusted_content(content))

        res = await self.call_llm_json(sys_prompt, user_prompt, temperature=VALIDATOR_EXTRACT_TEMPERATURE)
        return res.get("entities", [])

    async def review_full_story(
        self, *, title: str, outline: dict, manuscript: str, category: str
    ) -> dict:
        # 读哪份模板由调用方决定。短篇完结审校传自己的工作流名，于是从短篇克隆出来的
        # 工作流（prompt_mode=copy 会复制一份 validator_review_full_story）能读到自己那份；
        # 长篇卷级通读复用同一个方法，但只能传 zhihu_short —— 见 services/volume_review.py。
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_VALIDATOR_REVIEW_FULL_STORY,
            category=category,
        )
        return await self.call_llm_json(
            system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER,
            safe_format(
                user_tmpl,
                title=sanitize_untrusted_content(title),
                outline=outline,
                manuscript=sanitize_untrusted_content(manuscript),
            ),
            temperature=VALIDATOR_TEMPERATURE,
            max_tokens=VALIDATOR_MAX_TOKENS,
        )
