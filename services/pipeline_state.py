"""Compatibility facade for pipeline state imports.

New code should import from cohesive modules directly:
- services.pipeline_types
- services.pipeline_ordering
- services.pipeline_transitions
"""

from __future__ import annotations

from typing import Optional

from services import pipeline_ordering
from services.pipeline_transitions import (
    PipelineStateError,
    StateMachine,
    chapter_status_for_pipeline_step,
    coerce_pipeline_step as _coerce_pipeline_step,
    complete_chapter,
    pause_job,
    pipeline_step_for_job_step,
    publish_chapter_state,
    set_chapter_pipeline_step,
    set_job_step,
    transition_job_step,
    validate_pipeline_transition,
    validate_state_consistency,
)
from services.pipeline_types import (
    CHAPTER_STATUS_BY_PIPELINE_STEP,
    JOB_STEP_TO_PIPELINE_STEP,
    PIPELINE_ORDER,
    ChapterStatus,
    JobStatus,
    NovelStatus,
    PipelineStep,
    PipelineTransition,
    VectorOutboxStatus,
)


def pipeline_order_from_nodes(nodes: list[str]) -> list[PipelineStep]:
    """Derive a PipelineStep ordering from a PipelineConfig.nodes list."""
    return pipeline_ordering.pipeline_order_from_nodes(nodes, PipelineStep)


def get_pipeline_order() -> Optional[list[PipelineStep]]:
    """Return the contextvar-scoped pipeline order, or None if not set."""
    return pipeline_ordering.get_pipeline_order()


def set_pipeline_order(order: Optional[list[PipelineStep]]):
    """Set the contextvar-scoped pipeline order, returning the reset token."""
    return pipeline_ordering.set_pipeline_order(order)


def pipeline_order_scope(order: Optional[list[PipelineStep]]):
    """Context manager that sets the effective pipeline order."""
    return pipeline_ordering.pipeline_order_scope(order)


__all__ = [
    "PipelineStep",
    "JobStatus",
    "NovelStatus",
    "ChapterStatus",
    "VectorOutboxStatus",
    "CHAPTER_STATUS_BY_PIPELINE_STEP",
    "JOB_STEP_TO_PIPELINE_STEP",
    "PIPELINE_ORDER",
    "PipelineTransition",
    "pipeline_order_from_nodes",
    "get_pipeline_order",
    "set_pipeline_order",
    "pipeline_order_scope",
    "PipelineStateError",
    "pipeline_step_for_job_step",
    "chapter_status_for_pipeline_step",
    "_coerce_pipeline_step",
    "validate_pipeline_transition",
    "set_job_step",
    "set_chapter_pipeline_step",
    "publish_chapter_state",
    "transition_job_step",
    "pause_job",
    "complete_chapter",
    "validate_state_consistency",
    "StateMachine",
]
