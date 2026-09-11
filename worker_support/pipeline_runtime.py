"""Runtime pipeline configuration for generation workers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.pipeline_ordering import set_pipeline_order
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class GenerationPipelineRuntime:
    """单章生成读取的执行配置。

    **拓扑由 `graph` 决定**（`pipeline_configs.graph`，为空时由代码的 `default_graph()`
    派生），解释器按它执行。`has_editor` 等开关也从图**派生**而不是独立配置 ——
    否则「图里没有编辑步骤但 has_editor=True」这种自相矛盾的组合会静默存在。

    仍然独立存在的开关是那些**不影响拓扑**的：

    * `max_rewrites` / `enable_editor_loop` / `enable_force_correction` —— 图里的预算边
      读它们
    * `has_extractor` —— 注意它**不是**「有没有 postprocess 步骤」，而是那一步内部要不要
      跑设定提取。发布本身在那一步里，做成可缺省会让章节永远发不出去。
    """

    has_editor: bool
    has_extractor: bool
    max_rewrites: int
    enable_editor_loop: bool
    enable_force_correction: bool
    validation_before_editor: bool
    has_style_repair: bool = True
    stages: tuple = ()
    # 生效的拓扑图。generate_job_runner 优先用它，没有时按上面的开关构造默认图。
    graph: Any = None
    # 节点库（id -> WorkflowNode）。解释器用它把步骤上的节点 id 解析成提示词覆盖。
    nodes: dict = field(default_factory=dict)
    # 提示词 category 覆盖。`None` 表示用 novel_format 本身（绝大多数情况）。
    prompt_category: str | None = None


async def load_generation_pipeline_runtime(
    db: AsyncSession,
    novel_format: str,
) -> GenerationPipelineRuntime:
    try:
        from services.pipeline_config_service import get_pipeline_config

        pipeline_config = await get_pipeline_config(db, novel_format)
        set_pipeline_order(pipeline_config.to_pipeline_order())
        configured_max_rewrites = (
            pipeline_config.max_rewrite
            if pipeline_config.max_rewrite is not None
            else 2
        )
        from services.pipeline_config_service import NovelFormatPolicy

        format_policy = pipeline_config.policy or NovelFormatPolicy.from_format(novel_format)
        if format_policy.max_rewrites_override is not None:
            configured_max_rewrites = format_policy.max_rewrites_override
        enable_editor_loop = bool(pipeline_config.enable_editor_loop)
        enable_force_correction = bool(pipeline_config.enable_force_correction)

        plan = pipeline_config.stage_plan
        if plan is None:
            from services.pipeline_stages import StagePlan, stages_for_config

            plan = StagePlan.from_stages(
                stages_for_config(
                    None,
                    pipeline_config.nodes,
                    validation_before_editor=bool(pipeline_config.validation_before_editor),
                )
            )

        from services.chapter_graph import (
            ROLE_PRE_EDITOR,
            ROLE_REVIEW,
            ROLE_STYLE_REPAIR,
            default_graph,
        )

        graph = pipeline_config.graph
        if graph is None:
            graph = default_graph(
                has_editor=plan.has_editor,
                has_style_repair=plan.has_style_repair,
                validation_before_editor=plan.validation_before_editor,
            )

        from services.workflow_nodes import load_catalog

        return GenerationPipelineRuntime(
            # 三个开关从图**派生**，保证「图里有什么」与「开关说有什么」永远一致。
            has_editor=graph.has_role(ROLE_REVIEW),
            has_extractor=plan.has_extractor,
            max_rewrites=max(1, configured_max_rewrites),
            enable_editor_loop=enable_editor_loop,
            enable_force_correction=enable_force_correction,
            validation_before_editor=graph.has_role(ROLE_PRE_EDITOR),
            has_style_repair=graph.has_role(ROLE_STYLE_REPAIR),
            stages=plan.stages,
            graph=graph,
            nodes=await load_catalog(db),
            prompt_category=(
                pipeline_config.prompt_category
                if pipeline_config.prompt_category
                and pipeline_config.prompt_category != novel_format
                else None
            ),
        )
    except Exception:
        # 配置缺失或损坏时沿用既有的宽松兜底：所有阶段都开。
        set_pipeline_order(None)
        from services.chapter_graph import default_graph
        from services.pipeline_stages import StagePlan, default_stages
        from services.workflow_nodes import default_catalog

        plan = StagePlan.from_stages(default_stages(None, validation_before_editor=True))
        return GenerationPipelineRuntime(
            has_editor=True,
            has_extractor=True,
            max_rewrites=2,
            enable_editor_loop=True,
            enable_force_correction=True,
            validation_before_editor=True,
            has_style_repair=True,
            stages=plan.stages,
            graph=default_graph(
                has_editor=True, has_style_repair=True, validation_before_editor=True
            ),
            nodes=default_catalog(),
        )
