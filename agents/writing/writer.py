from agents.base import AgentBase, sanitize_untrusted_content, UNTRUSTED_CONTENT_SYSTEM_REMINDER, safe_format
from agents.pipeline_context import PipelineContext
from agents.constants import (
    BLACKLIST,
    STYLE_BLACKLIST,
    WRITER_TEMPERATURE,
    PROMPT_WRITER,
    WRITER_MAX_TOKENS,
    RAW_DOC_INLINE_THRESHOLD,
    CHARACTER_FACT_SOURCE_RULES,
)
from agents.prompt_hints import (
    append_missing_hints,
    authority_boundary_hint,
    compact_layered_prompt,
    continuity_contract_hint,
    continuity_handoff_hint,
    generation_hints as agent_generation_hints,
    hint_block,
    intervention_hint,
    narrative_index_hint,
    novel_memory_hint,
    previous_ending_for_prompt,
    reference_style_hint,
    vector_context_hint,
    writer_context_policy,
    writer_rewrite_requirements,
)

REWRITE_CLOSURE_CHECK = (
    "若存在上一轮重写原因或修改要求，必须在输出正文前暗中逐条核对："
    "该缺陷是否已被 100% 解决；核对过程不要输出，未完全解决前不得开始输出正文。"
)


def _prefer_full_doc(raw_doc: str, rag_doc: str) -> str:
    """Give the writer the complete living-doc when it's short enough to fit;
    fall back to the RAG-retrieved excerpt only for docs too large to inline.

    Fixes the "配角失忆 / 大纲没点名就丢设定" tunnel vision: the RAG path drops
    any entity the chapter outline didn't name, so a short full doc is strictly
    better context. raw_* are already populated on the context (worker_support/
    context.py) but were previously never read by any agent.
    """
    raw_doc = raw_doc or ""
    if raw_doc and len(raw_doc) <= RAW_DOC_INLINE_THRESHOLD:
        return raw_doc
    return rag_doc or raw_doc


def _skeleton_style_hint(skeleton: dict) -> tuple[str, str]:
    if not isinstance(skeleton, dict):
        return "小说", "生动、连贯、符合大纲"
    # 中英文 key 兼容提取（内联以避免 agents → services 反向依赖）
    genre = skeleton.get("类型") or skeleton.get("type", "")
    style = skeleton.get("风格") or skeleton.get("style", "")
    return str(genre or "小说"), str(style or "生动精彩、节奏流畅")


class WriterAgent(AgentBase):
    def __init__(self):
        super().__init__()  # 使用 config 中的模型

    async def write_chapter(
        self,
        context: PipelineContext,
        on_chunk = None,
    ) -> str:
        # 交接包与章节契约归 execution brief 所有。在 agent 边界清掉原始副本，
        # 避免长时间存活的 Worker 把完整审计负载重复带进 Writer。
        writer_policy = writer_context_policy()
        if writer_policy["suppress_handoff_and_contract"]:
            context.chapter_handoff_context = ""
            context.chapter_contract_context = ""
        chapter_outline = context.chapter_outline or {}
        skeleton = context.global_outline or {}
        previous_ending = (
            ""
            if writer_policy["suppress_previous_ending"]
            else previous_ending_for_prompt(
                context.previous_ending,
                context.chapter_handoff_context,
            )
        )
        world_state = _prefer_full_doc(context.raw_world_state, context.world_state)
        character_state = _prefer_full_doc(context.raw_character_state, context.character_state)
        foreshadowing = _prefer_full_doc(context.raw_foreshadowing, context.foreshadowing)
        plot_threads = _prefer_full_doc(context.raw_plot_threads, context.plot_threads)
        issue_summaries = context.issue_summaries
        word_count = context.word_count
        reference_style = context.reference_style
        vector_context = context.vector_context
        rewrite_instructions = context.rewrite_instructions
        novel_format = context.novel_format

        book_type, book_style = _skeleton_style_hint(skeleton)
        word_count_instruction = (
            f"字数尽量接近 {word_count} 字，且不得低于 {int(word_count * 0.75)} 字。"
            if word_count > 0
            else "每章字数不做限制，根据剧情自然展开。"
        )
        # 出戏表述提示：拒答话术（前6条，validator 亦硬拦截）+ 完整 AI 腔文风黑名单。
        # STYLE_BLACKLIST 不截断——它正是决定文笔像不像人写的核心内容。
        blacklist_hint = "、".join(list(BLACKLIST[:6]) + list(STYLE_BLACKLIST))
        narrative_stage = chapter_outline.get("narrative_stage", "平稳过渡") if isinstance(chapter_outline, dict) else "平稳过渡"

        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_WRITER,
            category=novel_format
        )

        rewrite_instructions_hint = hint_block(
            "【编辑打回后的修改要求 — 必须逐条落实】",
            _rewrite_instructions_with_closure_check(rewrite_instructions),
        )
        # Beat breakdown (book->volume->chapter->beat): the planner may attach an
        # ordered scene list; surface it so the writer builds the chapter scene by
        # scene instead of flattening key_events into filler.
        from services.outline_hierarchy import format_beats_hint
        beats_hint_value = format_beats_hint(
            chapter_outline.get("beats") if isinstance(chapter_outline, dict) else None
        )
        intervention_hint_value = intervention_hint(context.intervention)
        reference_style_hint_value = reference_style_hint(reference_style)
        vector_context_hint_value = vector_context_hint(vector_context)
        full_manuscript_context_hint = hint_block(
            "【短篇已写全文（续写时不得重复、跳跃或违背前文）】",
            context.full_manuscript_context,
        )
        character_card_context_hint = hint_block(
            "【本章涉及角色的完整角色卡与上一章状态（写作事实来源）】",
            context.character_card_context,
        )
        writer_execution_brief_hint_value = hint_block(
            "【V35 Writer 叙事执行简报（幕后参考）】",
            context.writer_execution_brief_context,
        )
        novel_memory_hint_value = novel_memory_hint(context.novel_memory_context, "writer")
        if writer_policy["suppress_handoff_and_contract"]:
            handoff_hint_value = ""
            contract_hint_value = ""
        else:
            handoff_hint_value = continuity_handoff_hint(context.chapter_handoff_context)
            contract_hint_value = continuity_contract_hint(context.chapter_contract_context)
        narrative_index_hint_value = narrative_index_hint(context.narrative_index_context, "writer")

        generation_hints = agent_generation_hints("writer", novel_format)
        sys_prompt = safe_format(
            system_tmpl,
            book_type=book_type,
            book_style=book_style,
            word_count_instruction=word_count_instruction,
            blacklist_hint=blacklist_hint,
            narrative_stage=narrative_stage
        ) + authority_boundary_hint() + generation_hints + CHARACTER_FACT_SOURCE_RULES + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        sys_prompt += writer_rewrite_requirements()

        user_prompt = safe_format(
            user_tmpl,
            skeleton=skeleton,
            world_state=sanitize_untrusted_content(world_state),
            character_state=sanitize_untrusted_content(character_state),
            plot_threads=sanitize_untrusted_content(plot_threads),
            foreshadowing=sanitize_untrusted_content(foreshadowing),
            issue_summaries=sanitize_untrusted_content(issue_summaries or "（无）"),
            chapter_outline=chapter_outline,
            previous_ending=sanitize_untrusted_content(previous_ending),
            full_manuscript_context=full_manuscript_context_hint,
            rewrite_instructions_hint=rewrite_instructions_hint,
            intervention_hint=intervention_hint_value,
            reference_style_hint=reference_style_hint_value,
            vector_context_hint=vector_context_hint_value,
            beats_hint=beats_hint_value,
            character_card_context=character_card_context_hint,
            writer_execution_brief_context=writer_execution_brief_hint_value,
            novel_memory_hint=novel_memory_hint_value,
            chapter_handoff_context=handoff_hint_value,
            chapter_contract_context=contract_hint_value,
            narrative_index_context=narrative_index_hint_value,
        )
        user_prompt = append_missing_hints(
            user_prompt,
            user_tmpl,
            rewrite_instructions_hint=rewrite_instructions_hint,
            intervention_hint=intervention_hint_value,
            reference_style_hint=reference_style_hint_value,
            vector_context_hint=vector_context_hint_value,
            full_manuscript_context=full_manuscript_context_hint,
            beats_hint=beats_hint_value,
            character_card_context=character_card_context_hint,
            writer_execution_brief_context=writer_execution_brief_hint_value,
            novel_memory_hint=novel_memory_hint_value,
            chapter_handoff_context=handoff_hint_value,
            chapter_contract_context=contract_hint_value,
            narrative_index_context=narrative_index_hint_value,
        )
        user_prompt = compact_layered_prompt(user_prompt)

        return await self.call_llm(sys_prompt, user_prompt, temperature=WRITER_TEMPERATURE, max_tokens=WRITER_MAX_TOKENS, on_chunk=on_chunk)


def _rewrite_instructions_with_closure_check(rewrite_instructions: str) -> str:
    rewrite_instructions = (rewrite_instructions or "").strip()
    if not rewrite_instructions:
        return ""
    return f"{rewrite_instructions}\n\n闭环自检：{REWRITE_CLOSURE_CHECK}"
