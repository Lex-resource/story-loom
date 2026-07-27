"""Runtime pipeline configuration for generation workers."""

from __future__ import annotations

from dataclasses import dataclass

from agents.constants import AGENT_EDITOR, AGENT_EXTRACTOR
from services.pipeline_ordering import set_pipeline_order
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class GenerationPipelineRuntime:
    has_editor: bool
    has_extractor: bool
    max_rewrites: int
    enable_editor_loop: bool
    enable_force_correction: bool
    validation_before_editor: bool
    enable_living_docs_update: bool


async def load_generation_pipeline_runtime(
    db: AsyncSession,
    novel_format: str,
) -> GenerationPipelineRuntime:
    try:
        from services.pipeline_config_service import get_pipeline_config

        pipeline_config = await get_pipeline_config(db, novel_format)
        pipeline_nodes = set(pipeline_config.nodes or [])
        set_pipeline_order(pipeline_config.to_pipeline_order())
        configured_max_rewrites = (
            pipeline_config.max_rewrite
            if pipeline_config.max_rewrite is not None
            else 2
        )
        from services.pipeline_config_service import NovelFormatPolicy

        format_policy = NovelFormatPolicy.from_format(novel_format)
        if format_policy.max_rewrites_override is not None:
            configured_max_rewrites = format_policy.max_rewrites_override
        enable_editor_loop = bool(pipeline_config.enable_editor_loop)
        enable_force_correction = bool(pipeline_config.enable_force_correction)
        validation_before_editor = bool(pipeline_config.validation_before_editor)
        enable_living_docs_update = bool(pipeline_config.enable_living_docs_update)
    except Exception:
        pipeline_nodes = set()
        configured_max_rewrites = 2
        enable_editor_loop = True
        enable_force_correction = True
        validation_before_editor = True
        enable_living_docs_update = True
        set_pipeline_order(None)

    has_editor = not pipeline_nodes or AGENT_EDITOR in pipeline_nodes
    has_extractor = (
        (not pipeline_nodes or AGENT_EXTRACTOR in pipeline_nodes)
        and enable_living_docs_update
    )

    return GenerationPipelineRuntime(
        has_editor=has_editor,
        has_extractor=has_extractor,
        max_rewrites=max(1, configured_max_rewrites),
        enable_editor_loop=enable_editor_loop,
        enable_force_correction=enable_force_correction,
        validation_before_editor=validation_before_editor,
        enable_living_docs_update=enable_living_docs_update,
    )
