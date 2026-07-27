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
)


class ValidatorAgent(AgentBase):
    def __init__(self):
        super().__init__()

    async def validate_content(
        self,
        context: PipelineContext,
        on_chunk = None,
    ) -> dict:
        title = context.title
        content = context.chapter_content
        active_entities_context = "\n".join(filter(None, [
            f"【短篇已写全文】\n{sanitize_untrusted_content(context.full_manuscript_context)}" if context.full_manuscript_context else None,
            f"【全局状态】\n{sanitize_untrusted_content(context.world_state)}" if context.world_state else None,
            f"【人物状态】\n{sanitize_untrusted_content(context.character_state)}" if context.character_state else None,
            f"【伏笔账本】\n{sanitize_untrusted_content(context.foreshadowing)}" if context.foreshadowing else None,
            f"【主线进度】\n{sanitize_untrusted_content(context.plot_threads)}" if context.plot_threads else None,
        ]))
        previous_ending = context.previous_ending
        novel_format = context.novel_format
        genre = context.genre
        style = context.style

        try:
            system_tmpl, user_tmpl = await self.get_prompt_template(
                PROMPT_VALIDATOR_VALIDATE_CONTENT,
                category=novel_format
            )

            sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
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

            res = await self.call_llm_json(
                sys_prompt, user_prompt, temperature=VALIDATOR_TEMPERATURE, max_tokens=VALIDATOR_MAX_TOKENS, on_chunk=on_chunk,
                response_schema=ValidatorResponse
            )
            return res
        except Exception as e:
            print(f"[ValidatorAgent ERROR] LLM analysis failed: {e}")
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

    async def review_full_story(self, *, title: str, outline: dict, manuscript: str) -> dict:
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_VALIDATOR_REVIEW_FULL_STORY,
            category="zhihu_short",
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
