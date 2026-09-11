from typing import Optional, Any
from agents.base import AgentBase, sanitize_untrusted_content, UNTRUSTED_CONTENT_SYSTEM_REMINDER, safe_format
from agents.pipeline_context import PipelineContext
from agents.writing_schemas import (
    EditorResponse,
    EditorResearchResponse,
    EditorShortFormResponse,
)
from agents.constants import (
    EDITOR_TEMPERATURE,
    PROMPT_EDITOR_REVIEW,
    PROMPT_EDITOR_FORCE_REVISE,
    PROMPT_EDITOR_DESTYLE,
    STYLE_BLACKLIST,
)
from services.workflow_surface import is_short_form_workflow
from agents.prompt_hints import (
    agent_context_policy,
    append_missing_hints,
    authority_boundary_hint,
    compact_layered_prompt,
    continuity_contract_hint,
    continuity_handoff_hint,
    editor_policy,
    generation_hints as agent_generation_hints,
    hint_block,
    intervention_hint,
    narrative_index_hint,
    novel_memory_hint,
    previous_ending_for_prompt,
    reference_style_hint,
    repair_surface_hints,
    validation_errors_hint,
    vector_context_hint,
)
from services.continuity_contract import prompt_outline_for_agent


_LONG_FORM_QUALITY_CONTRACT = (
    "\n\n【V19 七维质量记录硬约束（覆盖模板中的旧评分说明）】\n"
    "长篇连续性研究必须在 evaluations 中显式输出且只接受以下七个字段："
    "plot_progression、character_portrayal、world_consistency、writing_quality、"
    "logical_coherence、chapter_continuity、foreshadowing_payoff。\n"
    "每个字段都必须是 {score: 1-10 的整数, reason: 有证据的中文说明}。"
    "chapter_continuity 必须引用上一章结尾/交接包与本章承接，"
    "foreshadowing_payoff 必须引用伏笔的兑现、推进或明确延后。\n"
    "即使模板前文写着五维，也必须按本段输出七维；禁止省略后两项，禁止输出五维格式。"
)


def _apply_long_form_quality_contract(system_tmpl: str, novel_format: str) -> str:
    # 策略权威在 `editor_policy` 的格式轴上：长篇（及一切继承 frozen_v43 的自定义工作流）
    # 为 True，短篇覆盖为 False。这里曾经额外硬比 `novel_format == "long_webnovel"`，
    # 于是克隆自长篇的工作流拿不到这段七维契约，却仍被 `_response_schema` 判给
    # `EditorResearchResponse`（七维 required）—— 提示词五维、schema 七维，每章必重试。
    if editor_policy(novel_format)["long_form_quality_contract"]:
        return system_tmpl + _LONG_FORM_QUALITY_CONTRACT
    return system_tmpl


class EditorAgent(AgentBase):
    def __init__(self):
        super().__init__()  # 使用 config 中的模型

    @staticmethod
    def _response_schema(novel_format: str):
        """Require this workflow's full dimension set — no silent five-dim fallback.

        Long-form demands the seven continuity dimensions; short-form demands its
        own seven (five craft + hook_strength/emotional_landing). Both are strict
        so a missing dimension surfaces as a validation retry rather than a
        quietly incomplete quality record.

        按**表面策略**而不是格式名分派：克隆自短篇的自定义工作流会拿到短篇提示词
        （要求七维里含 hook_strength/emotional_landing），若这里还按格式名硬比，
        它就会配上只认长篇七维的 schema —— 提示词与 schema 对不上，每章都触发校验重试。
        """
        if is_short_form_workflow(novel_format):
            return EditorShortFormResponse
        if editor_policy(novel_format)["research_response_schema"]:
            return EditorResearchResponse
        return EditorResponse

    async def review_chapter(
        self,
        context: PipelineContext,
        on_chunk = None,
    ):
        # 交接包与章节契约的原始副本按表面策略决定（短篇不收）。在 agent 边界清掉，
        # 下游所有注入点自动变空 —— 与 Writer 同款（agents/writing/writer.py:71-74）。
        if agent_context_policy("editor", context.novel_format)["suppress_handoff_and_contract"]:
            context.chapter_handoff_context = ""
            context.chapter_contract_context = ""
        draft_content = context.draft_content
        chapter_outline = context.chapter_outline or {}
        world_state = context.world_state
        character_state = context.character_state
        foreshadowing = context.foreshadowing
        previous_ending = previous_ending_for_prompt(
            context.previous_ending,
            context.chapter_handoff_context,
        )
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
        character_card_context_hint = hint_block(
            "【本章涉及角色的完整角色卡与上一章状态（用于检查人物一致性）】",
            context.character_card_context,
        )
        novel_memory_hint_value = novel_memory_hint(context.novel_memory_context, "editor")
        handoff_hint_value = continuity_handoff_hint(context.chapter_handoff_context)
        contract_hint_value = continuity_contract_hint(context.chapter_contract_context)
        narrative_index_hint_value = narrative_index_hint(context.narrative_index_context, "editor")
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

        system_tmpl += editor_policy(novel_format)["review_strategy"]

        system_tmpl = _apply_long_form_quality_contract(system_tmpl, novel_format)

        generation_hints = agent_generation_hints("editor", novel_format)
        sys_prompt = system_tmpl + authority_boundary_hint() + generation_hints + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            genre=genre,
            style=style,
            world_state=sanitize_untrusted_content(world_state),
            character_state=sanitize_untrusted_content(character_state),
            foreshadowing=sanitize_untrusted_content(foreshadowing),
            issue_summaries=sanitize_untrusted_content(issue_summaries),
            chapter_outline=(
                prompt_outline_for_agent(chapter_outline, agent_type="editor")
                if editor_policy(novel_format)["project_outline"]
                else chapter_outline
            ),
            previous_ending=sanitize_untrusted_content(previous_ending),
            full_manuscript_context=full_manuscript_context_hint,
            draft_content=sanitize_untrusted_content(draft_content),
            validation_errors_hint=validation_errors_hint_value,
            intervention_hint=intervention_hint_value,
            reference_style_hint=reference_style_hint_value,
            vector_context_hint=vector_context_hint_value,
            style_blacklist_hint=style_blacklist_hint_value,
            character_card_context=character_card_context_hint,
            novel_memory_hint=novel_memory_hint_value,
            chapter_handoff_context=handoff_hint_value,
            chapter_contract_context=contract_hint_value,
            narrative_index_context=narrative_index_hint_value,
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
            character_card_context=character_card_context_hint,
            novel_memory_hint=novel_memory_hint_value,
            chapter_handoff_context=handoff_hint_value,
            chapter_contract_context=contract_hint_value,
            narrative_index_context=narrative_index_hint_value,
        )
        user_prompt = compact_layered_prompt(user_prompt)

        return await self.call_llm_json(
            sys_prompt, user_prompt, temperature=EDITOR_TEMPERATURE, on_chunk=on_chunk,
            response_schema=self._response_schema(novel_format)
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

        system_tmpl = _apply_long_form_quality_contract(system_tmpl, novel_format)
        sys_prompt = (
            system_tmpl
            + (repair_surface_hints("editor"))
            + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        )
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
            response_schema=self._response_schema(novel_format)
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

        system_tmpl = _apply_long_form_quality_contract(system_tmpl, novel_format)
        sys_prompt = (
            system_tmpl
            + (
                repair_surface_hints("editor")
            )
            + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        )
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
            response_schema=self._response_schema(novel_format)
        )


