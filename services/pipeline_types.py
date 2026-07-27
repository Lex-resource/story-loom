from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from agents.constants import (
    AGENT_EDITOR,
    AGENT_EXTRACTOR,
    AGENT_PLANNER,
    AGENT_VALIDATOR,
    AGENT_WRITER,
)


class PipelineStep(StrEnum):
    OUTLINE = "outline"
    WRITING = "writing"
    EDITING = "editing"
    VALIDATING = "validating"
    EXTRACTING = "extracting"
    PUBLISHED = "published"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class NovelStatus(StrEnum):
    PLANNING = "planning"
    GENERATING = "generating"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ChapterStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    POST_PROCESSING = "post_processing"
    POSTPROCESS_FAILED = "postprocess_failed"
    AUDIT_FAILED = "audit_failed"
    PENDING_REVIEW = "pending_review"
    FAILED = "failed"


class VectorOutboxStatus(StrEnum):
    PENDING = "pending"
    SYNCING = "syncing"
    DONE = "done"
    ERROR = "error"
    FAILED = "failed"


CHAPTER_STATUS_BY_PIPELINE_STEP = {
    PipelineStep.OUTLINE: ChapterStatus.DRAFT,
    PipelineStep.WRITING: ChapterStatus.DRAFT,
    PipelineStep.EDITING: ChapterStatus.DRAFT,
    PipelineStep.VALIDATING: ChapterStatus.VALIDATED,
    PipelineStep.EXTRACTING: ChapterStatus.POST_PROCESSING,
    PipelineStep.PUBLISHED: ChapterStatus.PUBLISHED,
}

JOB_STEP_TO_PIPELINE_STEP = {
    AGENT_PLANNER: PipelineStep.OUTLINE,
    AGENT_WRITER: PipelineStep.WRITING,
    AGENT_EDITOR: PipelineStep.EDITING,
    AGENT_VALIDATOR: PipelineStep.VALIDATING,
    AGENT_EXTRACTOR: PipelineStep.EXTRACTING,
}

PIPELINE_ORDER = [
    PipelineStep.OUTLINE,
    PipelineStep.WRITING,
    PipelineStep.EDITING,
    PipelineStep.VALIDATING,
    PipelineStep.EXTRACTING,
    PipelineStep.PUBLISHED,
]


@dataclass(frozen=True)
class PipelineTransition:
    job_step: str
    chapter_step: str
    chapter_status: Optional[str] = None
