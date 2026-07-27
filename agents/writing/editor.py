from typing import Optional, Any
from agents.base import AgentBase, sanitize_untrusted_content, UNTRUSTED_CONTENT_SYSTEM_REMINDER, safe_format
from agents.pipeline_context import PipelineContext
from agents.writing_schemas import EditorResponse
from agents.constants import (
    EDITOR_TEMPERATURE,
    PROMPT_EDITOR_REVIEW,
    PROMPT_EDITOR_FORCE_REVISE,
    PROMPT_EDITOR_DESTYLE,
    STYLE_BLACKLIST,
)
from agents.prompt_hints import (
    append_missing_hints,
    hint_block,
    intervention_hint,
    reference_style_hint,
    validation_errors_hint,
    vector_context_hint,
)


class EditorAgent(AgentBase):
    def __init__(self):
        super().__init__()  # 使用 config 中的模型

    async def review_chapter(
        self,
        context: PipelineContext,
        on_chunk = None,
    ):
        draft_content = context.draft_content
        chapter_outline = context.chapter_outline or {}
        world_state = context.world_state
        character_state = context.character_state
        foreshadowing = context.foreshadowing
        previous_ending = context.previous_ending
        issue_summaries = context.issue_summaries
        vector_context = context.vector_context
        validation_errors = context.validation_errors
        genre = context.genre
        style = context.style
        novel_format = context.novel_format
        reference_style = context.reference_style

        validation_errors_hint_value = validation_errors_hint(
            validation_errors,
            suffix="\n（请在决策中解决：直接在 edited_content 中进行词汇修改以清除错误，或者选择打回重写并在 rewrite_instructions 中对作家说明）",
        )
        intervention_hint_value = intervention_hint(context.intervention)
        reference_style_hint_value = reference_style_hint(reference_style)
        vector_context_hint_value = vector_context_hint(vector_context)
        full_manuscript_context_hint = hint_block(
            "【短篇已写全文（请按全文节奏和伏笔关系审阅本节）】",
            context.full_manuscript_context,
        )
        style_blacklist_hint_value = hint_block(
            "【AI腔黑名单 — 命中即为文笔缺陷，据此降低 writing_quality 并在 raw_issues 记 style 类问题】",
            "、".join(STYLE_BLACKLIST),
        )

        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_EDITOR_REVIEW,
            category=novel_format
        )

        if context.enable_light_polish:
            system_tmpl += "\n\n【轻量润色模式（知乎短篇）】\n当前处于轻量润色模式：请忽略任何关于篇幅长短或缺失事件的重写规则！你的首要任务是逐字逐句优化文笔（字字珠玑、情感饱满、网感增强），绝不要打回重写。请正常对各项维度进行严格评估并打分，但在 edited_content 中必须返回润色后的完整正文！"

        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            genre=genre,
            style=style,
            world_state=sanitize_untrusted_content(world_state),
            character_state=sanitize_untrusted_content(character_state),
            foreshadowing=sanitize_untrusted_content(foreshadowing),
            issue_summaries=sanitize_untrusted_content(issue_summaries),
            chapter_outline=chapter_outline,
            previous_ending=sanitize_untrusted_content(previous_ending),
            full_manuscript_context=full_manuscript_context_hint,
            draft_content=sanitize_untrusted_content(draft_content),
            validation_errors_hint=validation_errors_hint_value,
            intervention_hint=intervention_hint_value,
            reference_style_hint=reference_style_hint_value,
            vector_context_hint=vector_context_hint_value,
            style_blacklist_hint=style_blacklist_hint_value
        )
        user_prompt = append_missing_hints(
            user_prompt,
            user_tmpl,
            validation_errors_hint=validation_errors_hint_value,
            intervention_hint=intervention_hint_value,
            reference_style_hint=reference_style_hint_value,
            vector_context_hint=vector_context_hint_value,
            full_manuscript_context=full_manuscript_context_hint,
            style_blacklist_hint=style_blacklist_hint_value,
        )

        return await self.call_llm_json(
            sys_prompt, user_prompt, temperature=EDITOR_TEMPERATURE, on_chunk=on_chunk,
            response_schema=EditorResponse
        )

    async def force_revise_chapter(
        self,
        draft_content: str,
        chapter_outline: dict,
        world_state: str,
        character_state: str,
        foreshadowing: str,
        previous_ending: str,
        issue_summaries: str,
        rewrite_reason: str,
        novel_format: str,
        validation_errors: str = "",
        genre: str = "",
        style: str = "",
        on_chunk: Optional[Any] = None,
    ) -> dict:
        validation_errors_hint_value = validation_errors_hint(
            validation_errors,
            suffix="\n（请必须在 edited_content 中彻底清除并修改这些错误词汇）",
        )

        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_EDITOR_FORCE_REVISE,
            category=novel_format
        )

        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            genre=genre,
            style=style,
            world_state=sanitize_untrusted_content(world_state),
            character_state=sanitize_untrusted_content(character_state),
            foreshadowing=sanitize_untrusted_content(foreshadowing),
            issue_summaries=sanitize_untrusted_content(issue_summaries),
            chapter_outline=chapter_outline,
            previous_ending=sanitize_untrusted_content(previous_ending),
            rewrite_reason=rewrite_reason,
            draft_content=sanitize_untrusted_content(draft_content),
            validation_errors_hint=validation_errors_hint_value
        )

        return await self.call_llm_json(
            sys_prompt, user_prompt, temperature=EDITOR_TEMPERATURE, on_chunk=on_chunk,
            response_schema=EditorResponse
        )

    async def destyle_chapter(
        self,
        draft_content: str,
        chapter_outline: dict,
        world_state: str,
        character_state: str,
        foreshadowing: str,
        previous_ending: str,
        issue_summaries: str,
        style_report: dict,
        novel_format: str,
        genre: str = "",
        style: str = "",
        reference_style: str = "",
        on_chunk: Optional[Any] = None,
    ) -> dict:
        """Style-only repair pass: strip AI-cliché prose, vary sentence rhythm.

        Driven by the deterministic services.validator.analyze_style report so
        the LLM is forced to quote and rewrite the exact offending phrases
        rather than paraphrasing vaguely. Must not touch plot or facts.
        """
        style_report = style_report or {}
        cliche_hits = style_report.get("cliche_hits", {})
        issue_lines = [f"- 命中套话「{phrase}」×{count}，必须逐处改写" for phrase, count in cliche_hits.items()]
        if style_report.get("monotonous_rhythm"):
            issue_lines.append(
                f"- 句式单一（长度变异系数 {style_report.get('length_cv')}），必须打散长短句节奏"
            )
        style_issues_hint_value = hint_block(
            "【本章文笔检测命中项 — 必须逐条修复】",
            "\n".join(issue_lines),
        )
        style_blacklist_hint_value = hint_block(
            "【AI腔黑名单 — 出现即视为文笔缺陷，改写时务必清除】",
            "、".join(STYLE_BLACKLIST),
        )
        reference_style_hint_value = reference_style_hint(reference_style)

        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_EDITOR_DESTYLE,
            category=novel_format,
        )

        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            genre=genre,
            style=style,
            world_state=sanitize_untrusted_content(world_state),
            character_state=sanitize_untrusted_content(character_state),
            foreshadowing=sanitize_untrusted_content(foreshadowing),
            issue_summaries=sanitize_untrusted_content(issue_summaries),
            chapter_outline=chapter_outline,
            previous_ending=sanitize_untrusted_content(previous_ending),
            draft_content=sanitize_untrusted_content(draft_content),
            style_issues_hint=style_issues_hint_value,
            style_blacklist_hint=style_blacklist_hint_value,
            reference_style_hint=reference_style_hint_value,
        )
        user_prompt = append_missing_hints(
            user_prompt,
            user_tmpl,
            style_issues_hint=style_issues_hint_value,
            style_blacklist_hint=style_blacklist_hint_value,
            reference_style_hint=reference_style_hint_value,
        )

        return await self.call_llm_json(
            sys_prompt, user_prompt, temperature=EDITOR_TEMPERATURE, on_chunk=on_chunk,
            response_schema=EditorResponse
        )


