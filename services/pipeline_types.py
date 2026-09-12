"""Compatibility facade — 实现已下沉到 core.pipeline_vocab。

现有 `from services.pipeline_types import X` 全部保持可用。
"""

from __future__ import annotations

from core.pipeline_vocab import (  # noqa: F401  (facade re-exports)
    CHAPTER_STATUS_BY_PIPELINE_STEP,
    ChapterStatus,
    JOB_STEP_TO_PIPELINE_STEP,
    JobStatus,
    NovelStatus,
    PIPELINE_ORDER,
    PipelineStep,
    PipelineTransition,
    VectorOutboxStatus,
)
