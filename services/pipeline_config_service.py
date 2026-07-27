"""Pipeline 配置服务：提供 PipelineConfig 数据类与 DB 查询。

从 worker_support/pipeline_configs.py 迁移到 services 层，
消除 services/living_docs.py → worker_support 的反向依赖。
worker_support/pipeline_configs.py 保留 re-export 以兼容现有导入。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.constants import AGENT_EDITOR, AGENT_WRITER, NOVEL_FORMAT_ZHIHU_SHORT
from models.novel import PipelineConfigModel


@dataclass(frozen=True)
class NovelFormatPolicy:
    """聚合所有依赖 novel_format 的行为开关。

    历史上这些判断以 `novel_format == NOVEL_FORMAT_ZHIHU_SHORT` 的形式散落在
    6 个文件中。本类把它们收拢为一个数据对象，调用方只需查阅 policy.xxx 即可，
    新增第三种格式时只需在此处加一个工厂方法或扩展字段。

    Attributes:
        is_short_story: 是否为短篇（知乎短篇等），影响短期记忆窗口、提取器冻结等。
        enable_light_polish: 是否启用轻度润色（短篇 + settings.ENABLE_LIGHT_POLISH）。
        max_rewrites_override: 短篇未启用轻度润色时只允许一次写作尝试，否则不覆盖。
        freeze_extractor: 是否冻结设定提取器。
        use_short_skeleton_bootstrap: 是否使用短篇专用的骨架生成流程。
        bypass_short_term_memory_window: 短篇不按窗口截取历史章节（改为全量或跳过）。
    """

    is_short_story: bool
    enable_light_polish: bool
    max_rewrites_override: int | None
    freeze_extractor: bool
    use_short_skeleton_bootstrap: bool
    bypass_short_term_memory_window: bool

    @classmethod
    def from_format(cls, novel_format: str | None) -> "NovelFormatPolicy":
        """根据 novel_format 和全局 settings 构造策略。"""
        from config import settings

        is_short = bool(novel_format) and novel_format == NOVEL_FORMAT_ZHIHU_SHORT
        light_polish = is_short and getattr(settings, "ENABLE_LIGHT_POLISH", False)

        return cls(
            is_short_story=is_short,
            enable_light_polish=light_polish,
            # 当前生成循环把 1 表示为“完成初次写作但不自动重写”。
            max_rewrites_override=1 if (is_short and not light_polish) else None,
            freeze_extractor=False,
            use_short_skeleton_bootstrap=is_short,
            bypass_short_term_memory_window=is_short,
        )


@dataclass
class PipelineConfig:
    """流程配置"""
    nodes: List[str]  # 要执行的节点列表
    enable_living_docs_update: bool  # 是否更新 Living Docs
    enable_editor_loop: bool  # 是否支持 Editor 打回重写循环
    max_rewrite: int  # 最大重写次数
    readonly_docs: List[str]  # 只读文档类型
    required_docs: List[str]  # 必需的文档类型
    enable_force_correction: bool  # 达到最大重写次数后是否强制修正
    validation_before_editor: bool  # 是否在 Editor 前进行快速验证

    @classmethod
    def from_model(cls, model: "PipelineConfigModel") -> "PipelineConfig":
        """Construct a PipelineConfig from a PipelineConfigModel DB row.

        Centralizes the model→dataclass field mapping so the field list lives
        in one place instead of being duplicated at every construction site.
        """
        return cls(
            nodes=model.nodes,
            enable_living_docs_update=model.enable_living_docs_update,
            enable_editor_loop=model.enable_editor_loop,
            max_rewrite=model.max_rewrite,
            readonly_docs=model.readonly_docs,
            required_docs=model.required_docs,
            enable_force_correction=model.enable_force_correction,
            validation_before_editor=model.validation_before_editor,
        )

    def to_pipeline_order(self) -> list:
        """Derive a PipelineStep ordering from this config's ``nodes`` list.

        Returns a list of ``PipelineStep`` values that
        ``validate_pipeline_transition`` can use to validate forward-only
        transitions for this specific config (e.g. a short-story config that
        omits the editor step gets a 3-step order instead of the full 5).

        Lazy-imports the ordering helper to avoid loading pipeline config at
        module import time from lower-level state modules.
        """
        from services.pipeline_ordering import pipeline_order_from_nodes
        from services.pipeline_types import PipelineStep

        return pipeline_order_from_nodes(self.nodes, PipelineStep)


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

    config = PipelineConfig.from_model(config_model)

    # 用 NovelFormatPolicy 统一判断，取代散落的 novel_format == 检查
    policy = NovelFormatPolicy.from_format(novel_format)
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
        return modified

    return config
