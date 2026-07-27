from typing import Optional, Any
from agents.base import AgentBase, sanitize_untrusted_content, UNTRUSTED_CONTENT_SYSTEM_REMINDER, safe_format
from agents.pipeline_context import PipelineContext
from agents.writing_schemas import PlannerChapterOutlineResponse
from agents.constants import (
    PROMPT_PLANNER_GENERATE_SKELETON_OUTLINE,
    PROMPT_PLANNER_BRAINSTORM,
    PROMPT_PLANNER_FORMAT_JSON,
    PROMPT_PLANNER_GENERATE_CHAPTER_OUTLINE,
    PROMPT_PLANNER_CHAT_MODIFY_OUTLINE,
    PROMPT_PLANNER_OPTIMIZE_SKELETON_OUTLINE,
    PROMPT_PLANNER_REVIEW_ACT_RHYTHM,
)
from agents.prompt_hints import (
    append_missing_hints,
    hint_block,
    intervention_hint,
    reference_style_hint,
)
from services.outline_hierarchy import (
    format_active_volume_hint,
    select_active_volume,
)

LONG_FORM_STRUCTURE_REQUIREMENTS = """

【长篇必备规划结构】
整书骨架除原有字段外，必须包含：
1. "创作契约"：包含"核心卖点"、"主角底层动机"、"终局承诺"、"叙事边界"。这些是不可被自动优化改写的作品承诺。
2. "卷纲"：数组，每卷包含"卷名"、"章节范围"、"卷目标"、"主要对手"、"升级变化"、"阶段兑现"、"失败代价"、"核心事件"。每卷建议覆盖 20-30 章。
卷纲必须给出可持续冲突、对手升级、能力或资源变化和阶段性回报，不能只把故事阶段换个名字。
"""

LONG_FORM_OPTIMIZATION_GUARD = """

【自动优化边界】
不得修改书名与创作契约中的核心卖点、主角底层动机、终局承诺、叙事边界。只允许根据已写事实调整卷内事件顺序、次要冲突、过渡安排和尚未兑现的卷纲细节。
"""


class PlannerAgent(AgentBase):
    def __init__(self):
        super().__init__()  # 使用 config 中的模型

    async def generate_skeleton_outline(self, user_prompt: str, novel_format: str, total_chapters: int = 0, reference_style: str = "", on_chunk: Optional[Any] = None) -> dict:
        reference_style_hint_value = (
            f"\n\n参考风格：{sanitize_untrusted_content(reference_style)}" if reference_style else ""
        )
        total_chapters_hint_value = (
            f"\n\n目标总章数：{total_chapters}章（请确保故事体量、伏笔的埋设与回收都能在目标章数内完成）"
            if total_chapters > 0 else ""
        )

        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_PLANNER_GENERATE_SKELETON_OUTLINE,
            category=novel_format
        )

        if novel_format == "long_webnovel":
            system_tmpl += LONG_FORM_STRUCTURE_REQUIREMENTS
        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER

        # safe_format tolerates placeholders missing from the template; for
        # optional hints absent from the template, also append them at the end
        # so the content still reaches the model.
        user_prompt_str = safe_format(
            user_tmpl,
            user_prompt=sanitize_untrusted_content(user_prompt),
            reference_style_hint=reference_style_hint_value,
            total_chapters_hint=total_chapters_hint_value,
        )
        user_prompt_str = append_missing_hints(
            user_prompt_str,
            user_tmpl,
            reference_style_hint=reference_style_hint_value,
            total_chapters_hint=total_chapters_hint_value,
        )

        user_prompt = user_prompt_str

        return await self.call_llm_json(sys_prompt, user_prompt, on_chunk=on_chunk)

    async def generate_brainstorming(self, user_prompt: str, novel_format: str, total_chapters: int = 0, on_chunk: Optional[Any] = None) -> str:
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_PLANNER_BRAINSTORM,
            category=novel_format
        )
        total_chapters_hint_value = (
            f"\n\n目标总章数：{total_chapters}章（请确保故事体量、伏笔的埋设与回收都在此章数范围内）"
            if total_chapters > 0 else ""
        )
        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER

        user_prompt_str = safe_format(
            user_tmpl,
            user_prompt=sanitize_untrusted_content(user_prompt),
            total_chapters_hint=total_chapters_hint_value,
        )
        user_prompt_str = append_missing_hints(
            user_prompt_str,
            user_tmpl,
            total_chapters_hint=total_chapters_hint_value,
        )

        user_prompt = user_prompt_str

        return await self.call_llm(sys_prompt, user_prompt, on_chunk=on_chunk)

    async def generate_formatted_json(self, brainstorm_text: str, novel_format: str, on_chunk: Optional[Any] = None) -> dict:
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_PLANNER_FORMAT_JSON,
            category=novel_format
        )
        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(user_tmpl, brainstorm_text=sanitize_untrusted_content(brainstorm_text))
        return await self.call_llm_json(sys_prompt, user_prompt, on_chunk=on_chunk)

    async def generate_chapter_outline(
        self,
        context: PipelineContext,
        on_chunk: Optional[Any] = None,
        total_chapters: int = 1
    ) -> dict:
        skeleton = context.global_outline or {}
        chapter_index = context.chapter_index
        previous_ending = context.previous_ending
        active_entities_context = (
            f"【世界状态】\n{sanitize_untrusted_content(context.world_state)}\n\n"
            f"【人物状态】\n{sanitize_untrusted_content(context.character_state)}\n\n"
            f"【伏笔】\n{sanitize_untrusted_content(context.foreshadowing)}\n\n"
            f"【剧情线】\n{sanitize_untrusted_content(context.plot_threads)}"
        )
        issue_summaries = context.issue_summaries
        novel_format = context.novel_format

        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_PLANNER_GENERATE_CHAPTER_OUTLINE,
            category=novel_format
        )

        intervention_hint_value = intervention_hint(context.intervention)
        reference_style_hint_value = reference_style_hint(context.reference_style, label="策划风格参考")
        full_manuscript_context_hint = hint_block(
            "【短篇已写全文（必须保持连续并兑现前文承诺）】",
            context.full_manuscript_context,
        )
        active_volume = select_active_volume(skeleton, chapter_index)
        active_volume_hint_value = format_active_volume_hint(active_volume)

        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            skeleton=skeleton,
            active_entities_context=active_entities_context,
            issue_summaries=sanitize_untrusted_content(issue_summaries),
            chapter_index=chapter_index,
            previous_ending=sanitize_untrusted_content(previous_ending),
            full_manuscript_context=full_manuscript_context_hint,
            current_chapter=chapter_index,
            total_chapters=total_chapters,
            intervention_hint=intervention_hint_value,
            reference_style_hint=reference_style_hint_value,
            active_volume_hint=active_volume_hint_value,
        )
        user_prompt = append_missing_hints(
            user_prompt,
            user_tmpl,
            intervention_hint=intervention_hint_value,
            reference_style_hint=reference_style_hint_value,
            full_manuscript_context=full_manuscript_context_hint,
            active_volume_hint=active_volume_hint_value,
        )

        return await self.call_llm_json(sys_prompt, user_prompt, response_schema=PlannerChapterOutlineResponse, on_chunk=on_chunk)

    async def chat_modify_outline(self, current_outline: dict, instruction: str, novel_format: str) -> dict:
        import json

        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_PLANNER_CHAT_MODIFY_OUTLINE,
            category=novel_format
        )

        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            current_outline=json.dumps(current_outline, ensure_ascii=False, indent=2),
            instruction=sanitize_untrusted_content(instruction)
        )

        return await self.call_llm_json(sys_prompt, user_prompt)

    async def optimize_skeleton_outline(
        self,
        skeleton: dict,
        world_state: str,
        character_state: str,
        foreshadowing: str,
        plot_threads: str,
        chapter_summaries: str,
        novel_format: str,
    ) -> dict:
        import json

        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_PLANNER_OPTIMIZE_SKELETON_OUTLINE,
            category=novel_format
        )

        if novel_format == "long_webnovel":
            system_tmpl += LONG_FORM_STRUCTURE_REQUIREMENTS + LONG_FORM_OPTIMIZATION_GUARD

        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(
            user_tmpl,
            skeleton=json.dumps(skeleton, ensure_ascii=False, indent=2),
            chapter_summaries=sanitize_untrusted_content(chapter_summaries),
            world_state=sanitize_untrusted_content(world_state),
            character_state=sanitize_untrusted_content(character_state),
            foreshadowing=sanitize_untrusted_content(foreshadowing),
            plot_threads=sanitize_untrusted_content(plot_threads),
        )

        return await self.call_llm_json(sys_prompt, user_prompt)

    async def review_act_rhythm(self, chapter_outlines: list[dict], novel_format: str) -> dict:
        system_tmpl, user_tmpl = await self.get_prompt_template(
            PROMPT_PLANNER_REVIEW_ACT_RHYTHM,
            category=novel_format
        )

        def _row(ch: dict) -> str:
            base = f"- 第{ch.get('chapter_index')}章: {ch.get('title', '无题')} (阶段: {ch.get('narrative_stage', '未知')})"
            goal = ch.get("volume_goal")
            if goal:
                base += f" [所属卷目标: {goal}]"
            return base

        chapter_data = "\n".join([_row(ch) for ch in chapter_outlines])

        sys_prompt = system_tmpl + UNTRUSTED_CONTENT_SYSTEM_REMINDER
        user_prompt = safe_format(user_tmpl, chapter_data=chapter_data)

        return await self.call_llm_json(sys_prompt, user_prompt)
