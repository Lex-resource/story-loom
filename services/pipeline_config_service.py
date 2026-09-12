"""Pipeline 配置服务：提供 PipelineConfig 数据类与 DB 查询。"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import AGENT_EDITOR, AGENT_WRITER
from models.novel import PipelineConfigModel

if TYPE_CHECKING:
    from services.pipeline_stages import StagePlan


@dataclass(frozen=True)
class NovelFormatPolicy:
    """一个工作流的格式相关行为开关。

    历史上这些判断以 ``novel_format == NOVEL_FORMAT_ZHIHU_SHORT`` 的形式散落在 6 个
    文件中。本类把它们收拢为一个数据对象。工作流模块化之后，它的**权威来源是
    ``pipeline_configs.policy``**（可从前端编辑）；``from_format`` 只在没有数据库行
    或尚未迁移时作为代码兜底。

    原有六个字段中 ``is_short_story``、``freeze_extractor``、
    ``use_short_skeleton_bootstrap`` 从未被任何调用点读取（``freeze_extractor`` 甚至
    恒为 ``False``，``use_short_skeleton_bootstrap`` 承诺的短篇专用骨架流程并不存在），
    已随本次收编移除，避免继续伪装成可配置项。

    Attributes:
        enable_light_polish: 是否启用轻度润色（会把 editor 节点插到 writer 之后）。
        max_rewrites_override: 覆盖 ``pipeline_configs.max_rewrite``；``None`` 表示不覆盖。
        bypass_short_term_memory_window: 不按窗口截取历史章节，改为携带全文。
    """

    enable_light_polish: bool
    max_rewrites_override: int | None
    bypass_short_term_memory_window: bool

    @classmethod
    def from_format(cls, novel_format: str | None) -> "NovelFormatPolicy":
        """代码兜底：按 novel_format 和全局 settings 构造策略。

        数据库行的 ``policy`` 为空（未迁移、或自定义工作流未填）时使用。
        """
        from config import settings

        from services.workflow_surface import is_short_form_workflow

        # 按表面策略判断：克隆自短篇的工作流没填 policy 时也要拿到短篇兜底，
        # 而不是静默套上长篇的重写预算与记忆窗口。
        is_short = is_short_form_workflow(novel_format)
        light_polish = is_short and getattr(settings, "ENABLE_LIGHT_POLISH", False)

        return cls(
            enable_light_polish=light_polish,
            # 短篇三节里每节都是关键节，一稿定生死是缺陷而不是设计：给它一次重写机会。
            # 长篇不覆盖，沿用 pipeline_configs.max_rewrite。
            max_rewrites_override=2 if (is_short and not light_polish) else None,
            bypass_short_term_memory_window=is_short,
        )

    @classmethod
    def from_policy(
        cls,
        policy: dict | None,
        novel_format: str | None,
    ) -> "NovelFormatPolicy":
        """从 ``pipeline_configs.policy`` 构造，缺失的键回落到代码兜底。"""
        fallback = cls.from_format(novel_format)
        if not isinstance(policy, dict) or not policy:
            return fallback

        def flag(key: str, default: bool) -> bool:
            value = policy.get(key)
            return bool(value) if isinstance(value, bool) else default

        override = policy.get("max_rewrites_override", fallback.max_rewrites_override)
        if not isinstance(override, int) or isinstance(override, bool):
            override = fallback.max_rewrites_override

        # 数据库行是权威，代码兜底只在键缺失时生效 —— 所以未填写 enable_light_polish 的
        # 部署仍由 settings.ENABLE_LIGHT_POLISH 决定，迁移不会悄悄改变它们的行为。
        return cls(
            enable_light_polish=flag("enable_light_polish", fallback.enable_light_polish),
            max_rewrites_override=override,
            bypass_short_term_memory_window=flag(
                "bypass_short_term_memory_window",
                fallback.bypass_short_term_memory_window,
            ),
        )


@dataclass
class PipelineConfig:
    """流程配置"""
    nodes: List[str]  # 要执行的节点列表
    enable_editor_loop: bool  # 是否支持 Editor 打回重写循环
    max_rewrite: int  # 最大重写次数
    enable_force_correction: bool  # 达到最大重写次数后是否强制修正
    validation_before_editor: bool  # 是否在 Editor 前进行快速验证
    policy: NovelFormatPolicy | None = None  # 该工作流的格式策略（来自 policy 列）
    stage_plan: "StagePlan | None" = None  # 该工作流的阶段计划（来自 stages 列）
    graph: "ChapterGraph | None" = None  # 该工作流的拓扑图（来自 graph 列）
    # 提示词 category。与工作流名不同时表示「复用别人的提示词」。
    prompt_category: str | None = None

    @classmethod
    def from_model(cls, model: "PipelineConfigModel") -> "PipelineConfig":
        """Construct a PipelineConfig from a PipelineConfigModel DB row.

        Centralizes the model→dataclass field mapping so the field list lives
        in one place instead of being duplicated at every construction site.
        """
        from services.chapter_graph import graph_for_config
        from services.pipeline_stages import StagePlan, stages_for_config

        stage_plan = StagePlan.from_stages(
            stages_for_config(
                getattr(model, "stages", None),
                model.nodes,
                validation_before_editor=bool(model.validation_before_editor),
            )
        )
        return cls(
            nodes=model.nodes,
            enable_editor_loop=model.enable_editor_loop,
            max_rewrite=model.max_rewrite,
            enable_force_correction=model.enable_force_correction,
            validation_before_editor=model.validation_before_editor,
            policy=NovelFormatPolicy.from_policy(
                getattr(model, "policy", None),
                model.name,
            ),
            stage_plan=stage_plan,
            # `graph` 列为空时由阶段计划派生默认图 —— 代码是默认拓扑的权威。
            graph=graph_for_config(
                getattr(model, "graph", None),
                has_editor=stage_plan.has_editor,
                has_style_repair=stage_plan.has_style_repair,
                validation_before_editor=stage_plan.validation_before_editor,
                label=model.name,
            ),
            prompt_category=getattr(model, "prompt_category", None) or None,
        )

    def to_pipeline_order(self) -> list:
        """Derive a PipelineStep ordering for this config.

        顺序来自阶段计划（``stages`` 列，或从 ``nodes`` 派生的等价列表）。
        ``validate_pipeline_transition`` 用它做前向单调校验，例如省掉 editor 的
        工作流会得到一个不含 EDITING 的顺序。

        Lazy-imports the ordering helper to avoid loading pipeline config at
        module import time from lower-level state modules.
        """
        from services.pipeline_ordering import pipeline_order_from_nodes
        from services.pipeline_types import PipelineStep

        agents = (
            self.stage_plan.agent_order() if self.stage_plan is not None else self.nodes
        )
        return pipeline_order_from_nodes(agents, PipelineStep)


async def get_pipeline_config(db: AsyncSession, novel_format: str) -> PipelineConfig:
    """根据小说类型从数据库获取流程配置"""
    result = await db.execute(
        select(PipelineConfigModel).where(PipelineConfigModel.name == novel_format)
    )
    config_model = result.scalar_one_or_none()

    if not config_model:
        raise ValueError(
            f"无法在数据库中找到小说格式 '{novel_format}' 对应的流程配置，"
            f"请确保已初始化 pipeline_configs 表。"
        )

    # 顺手预热工作流缓存：`workflow_surface.strategy_for()` 在提示词组装的同步热路径上
    # 被调用，拿不到 AsyncSession。这里用**已经读到的这一行**填缓存，零额外查询，而每章
    # 生成都会经过这里，于是自定义工作流的表面策略一定在被用到之前就绪。
    from services import workflow_registry

    workflow_registry.remember(config_model)

    config = PipelineConfig.from_model(config_model)

    # 策略权威来自 pipeline_configs.policy（可从前端编辑）；该列为空时 from_policy
    # 已回落到 from_format 的代码兜底。
    policy = config.policy or NovelFormatPolicy.from_format(novel_format)
    if policy.enable_light_polish:
        modified = copy.deepcopy(config)
        # 插入 editor 节点
        if AGENT_EDITOR not in modified.nodes:
            try:
                writer_idx = modified.nodes.index(AGENT_WRITER)
                modified.nodes.insert(writer_idx + 1, AGENT_EDITOR)
            except ValueError:
                modified.nodes.append(AGENT_EDITOR)
        modified.enable_editor_loop = True
        # 阶段计划必须跟着一起重建，否则 has_editor 会与 nodes 不一致：
        # nodes 里有 editor，而由旧 stages 派生的执行开关仍说没有 Editor 阶段。
        from services.pipeline_stages import StagePlan, default_stages

        modified.stage_plan = StagePlan.from_stages(
            default_stages(
                modified.nodes,
                validation_before_editor=bool(modified.validation_before_editor),
            )
        )
        # 拓扑图同理 —— 但**只在图是派生出来的默认图时**重建。用户手写过 graph 就以它
        # 为准：轻度润色是「给没有编辑的流程补一个编辑」，不该悄悄推翻手工编排的拓扑。
        if not getattr(config_model, "graph", None):
            from services.chapter_graph import default_graph

            modified.graph = default_graph(
                has_editor=modified.stage_plan.has_editor,
                has_style_repair=modified.stage_plan.has_style_repair,
                validation_before_editor=modified.stage_plan.validation_before_editor,
            )
        return modified

    return config
